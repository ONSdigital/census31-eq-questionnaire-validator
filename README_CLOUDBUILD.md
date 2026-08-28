Cloud Build Pipelines
This directory contains the Cloud Build YAML files used by the CI/CD system in the
census31-eq-ci-terraform project.

Two pipelines are defined:

pr-build.yaml — PR validation pipeline

merge-push-to-gar.yaml — merge-to-main build and publish pipeline

1. PR Build Pipeline — pr-build.yaml
Purpose
a. Runs on every pull request.
b. Validates code quality but does not publish Docker images.

Steps
a. Install Python dependencies

b. Run unit tests

c. Run linting

d. Build Docker image (local only)

2. Merge Build & Push Pipeline — merge-push-to-gar.yaml
Purpose
a. Runs on push to main.
b. Builds, tests, and pushes the Docker image to Artifact Registry.

Steps
a. Install dependencies

b. Run tests

c. Build Docker image

d. Push to GAR

e. Slack notification supported via substitutions

Note:

$PROJECT_ID is automatically injected by Cloud Build

No gcloud auth is required inside Cloud Build

IAM must be applied to the validator service account

Slack notifications are handled via substitutions from Terraform