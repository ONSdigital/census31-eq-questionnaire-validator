"""API for validating questionnaire schemas using jsonschema and a Questionnaire Validator instance.
This module provides a FastAPI application for validating questionnaire schemas using local jsonschema files and
internal QuestionnaireValidator logic. It exposes endpoints for health checks and schema validation, supporting both
direct JSON payloads and remote schema URLs.


Functions:
    configure_logging
    status
    validate_schema_request_body
    validate_schema_from_url
    validate_schema
    is_url_allowed
    parse_json

Endpoints:
    - GET /status: Health check endpoint. Returns HTTP 200 if service is running.
    - POST /validate: Validates a questionnaire schema provided in the request body (JSON).
    - GET /validate: Validates a questionnaire schema provided via a URL query parameter.
"""

import json
import logging
import os
import sys
from json import JSONDecodeError
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse

import structlog
import uvicorn
from fastapi import Body, FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app.validators.questionnaire_validator import QuestionnaireValidator

ALLOWED_FULL_DOMAINS = {
    "https://gist.githubusercontent.com/",
    "https://raw.githubusercontent.com/",
}

ALLOWED_BASE_DOMAINS = {"onsdigital.uk"}

ALLOWED_REPO_OWNERS = {"ONSdigital"}

VALIDATOR_VERSION = os.getenv("VALIDATOR_VERSION", "0.0.0")

DEFAULT_BODY = Body(None)

app = FastAPI()

logger = structlog.get_logger()

SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"


def _serialize_validation_error(validation_error):
    """Convert a jsonschema ValidationError into a JSON-serializable structure."""
    return {
        "message": validation_error.message,
        "validator": validation_error.validator,
        "json_path": validation_error.json_path,
        "instance": validation_error.instance,
        "cause": str(validation_error.cause) if validation_error.cause else None,
        "context": [_serialize_validation_error(context_error) for context_error in validation_error.context],
    }


def _build_schema_validator():
    """Build a Draft 2020-12 validator with all local schemas preloaded."""
    resources = {}
    base_schema = None

    for schema_path in sorted(SCHEMAS_DIR.rglob("*.json")):
        with schema_path.open(encoding="utf-8") as schema_file:
            schema = json.load(schema_file)

        relative_schema_path = schema_path.relative_to(SCHEMAS_DIR).as_posix()
        schema_id = schema.get("$id")
        resource = Resource.from_contents(schema)

        resources[relative_schema_path] = resource
        resources[f"/{relative_schema_path}"] = resource

        if isinstance(schema_id, str) and schema_id:
            resources[schema_id] = resource
            resources[schema_id.lstrip("/")] = resource

        if relative_schema_path == "questionnaire_v1.json":
            base_schema = schema

    if base_schema is None:
        error_message = "Base schema not found at schemas/questionnaire_v1.json"
        logger.error(error_message)
        raise ValueError(error_message)

    registry = Registry().with_resources(resources.items())
    return Draft202012Validator(base_schema, registry=registry)


SCHEMA_VALIDATOR = _build_schema_validator()


def configure_logging():
    """Configures logging for the application using structlog. The log level is set based on the LOG_LEVEL environment
    variable, with DEBUG level if LOG_LEVEL is set to "DEBUG" and "INFO" level otherwise. Logs are output to stdout,
    while error logs are output to stderr. The log format is set to a human-readable console format in "DEBUG" mode and
    JSON format in other modes.
    """
    log_level = logging.DEBUG if os.getenv("LOG_LEVEL") == "DEBUG" else logging.INFO

    error_log_handler = logging.StreamHandler(sys.stderr)
    error_log_handler.setLevel(logging.ERROR)

    renderer_processor = (
        structlog.dev.ConsoleRenderer() if log_level == logging.DEBUG else structlog.processors.JSONRenderer()
    )

    logging.basicConfig(level=log_level, format="%(message)s", stream=sys.stdout)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            renderer_processor,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


configure_logging()


@app.get("/status")
async def status():
    """Endpoint for checking if the service is running.

    Returns:
        A response with status code 200 if the service is running.
    """
    return Response(status_code=200)


@app.post("/validate")
async def validate_schema_request_body(payload=DEFAULT_BODY):
    """Endpoint for validating a questionnaire schema provided in the request body as JSON.

    Args:
        payload: The JSON payload containing the questionnaire schema to be validated. This can be either a JSON string
        or a JSON object (dictionary).

    Returns:
        A response with status code 200 if the schema is valid, or a response with status code 400 containing error
        details if the schema is invalid.
    """
    logger.info("Schema validation request received")
    return await validate_schema(payload)


@app.get("/validate")
async def validate_schema_from_url(url=None):
    """Endpoint for validating a questionnaire schema provided in a URL query parameter. The URL is validated against
    allowed domains and repo owners before the schema is loaded and validated.

    Args:
        url: The URL query parameter containing the URL of the questionnaire schema to be validated.

    Returns:
        A response with status code 200 if the schema is valid, or a response with status code 400 containing error(s)
        details if the schema failed validation or if the URL is not allowed. It also returns errors if url is not
        allowed, schemes other than http and https are used, or if the schema cannot be loaded from the URL.
        If the AJV Validator service is unavailable, returns a response with status code 503.
    """
    logger.debug("Attempting to validate schema from URL...", url=url)
    if url:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        if not is_url_allowed(parsed_url, domain):
            return Response(
                status_code=400,
                content=f"URL domain [{parsed_url.hostname}] is not allowed",
            )
        if parsed_url.scheme not in {"http", "https"}:
            return Response(
                status_code=400,
                content="Only http and https schemes are allowed",
            )
        logger.info("Schema validation request accepted - URL allowed", url=url)
        try:
            # Opens the URL and validates the schema
            # Mitigation for opening ftp:// and file:// URLs with urllib.request is implemented in lines 91-95
            with request.urlopen(parsed_url.geturl()) as opened_url:  # nosec B310  # noqa: S310
                return await validate_schema(data=opened_url.read().decode())
        except error.URLError:
            logger.warning(
                "Could not load schema from allowed domain - URL not found",
                url=url,
            )
            return Response(
                status_code=404,
                content=f"Could not load schema from allowed domain - URL not found [{url}]",
            )
    return None


async def validate_schema(data):  # pylint: disable=R0911
    """Validate a questionnaire schema provided as JSON data.

    The JSON data is first validated against local jsonschema schema files, and then the contents of the schema are
    validated using a Questionnaire Validator instance.

    Args:
        data (str or dict): The JSON data containing the questionnaire schema to be validated. This can be either
        a JSON string or a JSON object (dictionary).

    Returns:
        A response with status code 200 if the schema is valid, or a response with status code 400 containing error(s)
        details if the schema failed validation. It can also return 400 if the JSON data is invalid or not provided.
    """
    logger.debug("Attempting to validate schema from JSON data...")
    if data:
        if isinstance(data, dict):
            logger.info("JSON data received as dictionary - parsing not required")
            json_to_validate = data
        elif isinstance(data, str):
            logger.info("JSON data received as string - parsing required")
            logger.debug("Attempting to parse JSON data...")
            json_to_validate = parse_json(data)
            # If parse_json returns a Response (error), return it immediately
            if isinstance(json_to_validate, Response):
                return json_to_validate
        else:
            logger.error(
                "Invalid data type received for validation (expected string or dictionary)",
                data_type=type(data),
                status=400,
            )
            return Response(
                status_code=400,
                content="Invalid data type received for validation",
            )
    else:
        logger.error("No JSON data provided for validation", status=400)
        return Response(status_code=400, content="No JSON data provided for validation")

    response = {}
    logger.debug("Validating questionnaire against local jsonschema files")
    validation_errors = sorted(
        SCHEMA_VALIDATOR.iter_errors(json_to_validate),
        key=lambda schema_error: len(schema_error.absolute_path),
    )

    if validation_errors:
        response["errors"] = [_serialize_validation_error(schema_error) for schema_error in validation_errors]
        logger.info(
            "Schema validation returned errors",
            status=400,
            errors=response["errors"],
        )
        return JSONResponse(
            content=jsonable_encoder({**response, "validator_version": VALIDATOR_VERSION, "success": False}),
            status_code=400,
        )

    logger.info("Schema validation returned no errors")

    validator = QuestionnaireValidator(json_to_validate)
    logger.debug(
        "Attempting to validate questionnaire schema contents with Questionnaire Validator...",
        form_type=json_to_validate.get("form_type"),
        survey_id=json_to_validate.get("survey_id"),
        title=json_to_validate.get("title"),
    )
    # Validates questionnaire schema contents using the QuestionnaireValidator
    validator.validate()

    # Adds errors from validation to the response if there are any
    if validator.errors:
        response["errors"] = validator.errors
        logger.info(
            "Questionnaire Validator returned errors",
            status=400,
            errors=response["errors"],
        )

        return JSONResponse(
            content=jsonable_encoder({**response, "validator_version": VALIDATOR_VERSION, "success": False}),
            status_code=400,
        )

    logger.info("Schema validation successfully completed with no errors", status=200)

    return JSONResponse(
        content=jsonable_encoder({**response, "validator_version": VALIDATOR_VERSION, "success": True}),
        status_code=200,
    )


def is_url_allowed(parsed_url, domain):
    """Check if a URL is allowed based on its domain and repo owner. The function checks if the base URL
    (scheme + netloc) is in the ALLOWED_FULL_DOMAINS set and if the repo owner (the first part of the path)
    is in the ALLOWED_REPO_OWNERS set.

    Args:
        parsed_url (str): The URL to check, parsed using urlparse.
        domain (str): The domain of the URL (netloc) to check against allowed base domains.
    """
    logger.debug("Checking if domain is allowed...", domain=domain)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
    repo_owner = parsed_url.path.split("/")[1] if len(parsed_url.path.split("/")) > 1 else ""
    logger.debug("Parsed URL components", base_url=base_url, repo_owner=repo_owner)

    # Allows URLs from verified full domains with trusted repo owners
    full_url_allowed = base_url in ALLOWED_FULL_DOMAINS and repo_owner in ALLOWED_REPO_OWNERS
    # Allows URLs from trusted base domains
    base_domain_allowed = domain in ALLOWED_BASE_DOMAINS

    logger.debug(
        "URL allowance checks",
        full_url_allowed=full_url_allowed,
        base_domain_allowed=base_domain_allowed,
    )

    url_allowed = full_url_allowed or base_domain_allowed

    # If the URL is not allowed, outputs warnings reflecting which parts of the URL are not allowed
    if not url_allowed:
        logger.warning("URL is not allowed", url=parsed_url.geturl())
        if base_url not in ALLOWED_FULL_DOMAINS:
            logger.warning(
                "Base URL is not in ALLOWED_FULL_DOMAINS (resolve by using allowed base URL or domain)",
                base_url=base_url,
            )
        if repo_owner not in ALLOWED_REPO_OWNERS:
            logger.warning(
                "Repo owner is not in ALLOWED_REPO_OWNERS (resolve by using allowed repo owner or domain)",
                repo_owner=repo_owner,
            )
        if not base_domain_allowed:
            logger.warning(
                "Domain is not in ALLOWED_BASE_DOMAINS (resolve by using allowed domain or full URL)",
                domain=domain,
            )

    return url_allowed


def parse_json(data):
    """Parses JSON data from a string and returns the resulting object. If the data cannot be parsed as JSON,
    returns a response with status code 400.

    Args:
        data (str): The JSON data to parse, provided as a string.

    Returns:
        The parsed JSON object if parsing is successful, or a response with status code 400 if parsing fails.
    """
    try:
        processed_data = json.loads(data)
        logger.info("JSON data parsed successfully")
    except JSONDecodeError:
        logger.exception("Failed to parse JSON data", status=400)
        return Response(status_code=400, content="Failed to parse JSON")
    return processed_data


if __name__ == "__main__":
    uvicorn.run("api:app", workers=20, port=5001, reload=True)
