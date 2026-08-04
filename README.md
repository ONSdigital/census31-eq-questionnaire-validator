# census31-eq-questionnaire-validator

An API for validating questionnaire schemas.

## Setup

In order to run locally you'll need Poetry and Python installed.
It's recommended that Python is installed via pyenv but pyenv is optional.

### Install pyenv

pyenv will manage your Python versions and these commands will install the
required version from `.python-version`.

```shell
brew install pyenv
pyenv install
```

### Install Poetry and Python dependencies

```shell
curl -sSL https://install.python-poetry.org | python3 - --version 2.1.2
poetry install
```

## Running locally

To run the app:

```shell
make run
```

Validator runs on port `5001`.

### Validator

Validator runs on `http://localhost:5001/validate` and accepts GET and POST requests.

If you need to change the port you can change the port variable in the Uvicorn settings in api.py:

```python
uvicorn.run("api:app", workers=20, port=5001, reload=True)
```

The reload flag here will allow the service to restart if you make a change to the code,
if you want to run the app locally using multiple server workers you need to set reload to "False".

### Running against a URL

Once Validator is running, it can be called directly in the browser using the "/validate" endpoint
and the "url" parameter for the address where the schema is located (e.g. GitHub Gist raw json).

As Validator runs on `localhost:5001` by default, here is an
example of a command you can use to validate a schema via a URL:

```shell
http://localhost:5001/validate?url=https://raw.githubusercontent.com/ONSdigital/census31-eq-questionnaire-runner/refs/heads/main/schemas/test/en/test_address.json
```

Only the following URLs and domains are accepted:

- `https://gist.githubusercontent.com/`
- `https://raw.githubusercontent.com/`
- `onsdigital.uk`
- `localhost`

Also when using a URL from GitHub you can only validate schemas from the ONSdigital organisation and
only against repos with the owner "ONSdigital".

### Running against eQ Runner

Also once you have Validator running it can be used to run against eQ Runner (`https://github.com/ONSdigital/census31-eq-questionnaire-runner`).
If you have eQ Runner spun up you can from within the root of eQ Runner run:

```shell
make validate-test-schemas
```

This script will run Validator on the test eQ Runner schemas.

### Testing and running against local schemas

By default, all schemas in the `tests/schemas/valid` and `tests/schemas/invalid` directories will be
evaluated as part of the Python tests. Any errors in these schemas will cause a failure.

To run the app's Python tests:

```shell
make test-python
```

To run the app's unit tests:

```shell
make test
```

#### Test the local Validator app against eQ Runner schemas

Spin Validator up with:

```shell
make run
```

Then, in another terminal, navigate to a checked out copy
of `https://github.com/ONSdigital/census31-eq-questionnaire-runner` and run:

```shell
make validate-test-schemas
```

This will run Validator against all eQ Runner test schemas.

Or you can run it against a specific eQ Runner schema, to do this:

- set the following vars passing them into the following command:
  - `SCHEMA_PATH` to the path of the schema file (if not specified defaults to `./schemas/test/en/`)
  - `SCHEMA` to the schema file name without the `.json`
- then run (for example):

```shell
make validate-test-schema SCHEMA=test_checkbox SCHEMA_PATH=./schemas/
```

## Formatting/linting json

Run the following to format the json files in the schemas and test schemas folders
and the Python files in the repository:

```shell
make format
```

Run the following to lint the json files in the schemas and test schemas folders
and the Python files in the repository:

```shell
make lint
```

## MegaLinter (Lint/Format non-python files)

[MegaLinter](https://github.com/oxsecurity/megalinter) is utilised to lint the non-python files in the project.
It offers a single interface to execute a suite of linters for multiple languages and formats, ensuring adherence to
best practices and maintaining consistency across the repository without the need to install each linter individually.

MegaLinter examines various file types and tools, including GitHub Actions, Shell scripts, Dockerfile, etc. It is
configured using the `.mega-linter.yml` file.

To run MegaLinter, ensure you have **Docker** installed on your system.

> Note: The initial run may take some time to download the Docker image. However, subsequent executions will be
> considerably faster due to Docker caching.

To start the linter and automatically rectify fixable issues, run:

```bash
make megalint
```

## Running with Docker

To install Docker run:

```shell
brew install docker
```

On MacOS install container runtimes, e.g. Colima:

```shell
brew install colima
```

Make sure Colima is started every time you want to use Docker images:

```shell
colima start
```

When PRs are merged in this repo there is a GitHub workflow that builds a Docker image for Validator
and then pushes it to our GAR in GCP.
This image can then be pulled down and run locally with Docker.
These images are pulled down and run from eQ Runner when `make run validator` is run which uses
the `docker-compose-schema-validator.yml` script.

You can do this using these commands:

You will need to be authenticated with GCP to run these, to do this run `gcloud auth login` first

- Validator:

```shell
docker run -it -p 5001:5001 europe-west2-docker.pkg.dev/ons-eq-ci/docker-images/eq-questionnaire-validator
```

To stop these containers you may need to use the `docker kill` command:

First run:

```shell
docker ps
```

Then make a note of the container id of the container you want to stop and then
run (replacing "<CONTAINER_ID>" with the id):

```shell
docker kill <CONTAINER_ID>
```

## Environment variables

| Environment variable | Description                                                                                   | Default value |
|----------------------|-----------------------------------------------------------------------------------------------|---------------|
| `LOG_LEVEL`          | Sets the minimum log level, can be set to `DEBUG` to increase this level                      | `INFO`        |
| `VALIDATOR_VERSION`  | Sets the version of the validator, this is used in the response from the `/validate` endpoint | `0.0.0`       |
