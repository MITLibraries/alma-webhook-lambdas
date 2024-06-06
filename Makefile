# ---- This is the Terraform-generated header for the timdex-pipeline-lambads Makefile ---- ##
SHELL=/bin/bash
DATETIME:=$(shell date -u +%Y%m%dT%H%M%SZ)

## ---- This is the Terraform-generated header for alma-webhook-lambdas-dev ---- ##
ECR_NAME_DEV:=alma-webhook-lambdas-dev
ECR_URL_DEV:=222053980223.dkr.ecr.us-east-1.amazonaws.com/alma-webhook-lambdas-dev
FUNCTION_DEV:=alma-webhook-lambdas-dev
## ---- End of Terraform-generated header ---- ##

help: # print this message
	@awk 'BEGIN { FS = ":.*#"; print "Usage:  make <target>\n\nTargets:" } \
/^[-_[:alpha:]]+:.?*#/ { printf "  %-15s%s\n", $$1, $$2 }' $(MAKEFILE_LIST)

#######################
# Dependency commands
#######################

install: # Install Python dependencies
	pipenv install --dev
	pipenv run pre-commit install

update: install # Update all python dependencies
	pipenv clean
	pipenv update --dev

##################
# Test commands
##################

test: # Run tests and print a coverage report
	pipenv run coverage run --source=lambdas -m pytest -vv -m "not integration"
	pipenv run coverage report -m

coveralls: test
	pipenv run coverage lcov -o ./coverage/lcov.info

test-integration:
	pipenv run pytest -vv -s -m "integration"

####################################
# Code quality and safety commands
#################################### 

# linting commands
lint: black mypy ruff safety # Run linters

black: # Run 'black' linter and print a preview of suggested changes
	pipenv run black --check --diff .

mypy: # Run 'mypy' linter
	pipenv run mypy .

ruff: # Run 'ruff' linter and print a preview of errors
	pipenv run ruff check .

safety: # Check for security vulnerabilities and verify Pipfile.lock is up-to-date
	pipenv check
	pipenv verify

lint-apply: black-apply ruff-apply # Apply changes with 'black' and resolve 'fixable errors' with 'ruff'

black-apply: # Apply changes with 'black'
	pipenv run black .

ruff-apply: # Resolve 'fixable errors' with 'ruff'
	pipenv run ruff check --fix .

#####################################################################
# Terraform-generated Developer Deploy Commands for Dev environment
#####################################################################
dist-dev: # Build Docker container (intended for developer-based manual build)
	docker build --platform linux/amd64 \
	    -t $(ECR_URL_DEV):latest \
		-t $(ECR_URL_DEV):`git describe --always` \
		-t $(ECR_NAME_DEV):latest .

publish-dev: dist-dev # Build, tag, and push Docker container (intended for developer-based manual publish)
	docker login -u AWS -p $$(aws ecr get-login-password --region us-east-1) $(ECR_URL_DEV)
	docker push $(ECR_URL_DEV):latest
	docker push $(ECR_URL_DEV):`git describe --always`

update-lambda-dev: # Update the Lambda function code with the most recent image on ECR (intended for developer-based manual update)
	aws lambda update-function-code --function-name $(FUNCTION_DEV) --image-uri $(ECR_URL_DEV):latest

### Terraform-generated manual shortcuts for deploying to Stage ###
### This requires that ECR_NAME_STAGE, ECR_URL_STAGE, and FUNCTION_STAGE environment variables are
### set locally by the developer and that the developer has authenticated to the correct AWS Account.
### The values for the environment variables can be found in the stage_build.yml caller workflow.
dist-stage: # Build Docker container for stage (only use in an emergency)
	docker build --platform linux/amd64 \
	    -t $(ECR_URL_STAGE):latest \
		-t $(ECR_URL_STAGE):`git describe --always` \
		-t $(ECR_NAME_STAGE):latest .

publish-stage: # Build, tag, and push Docker container for stage (only use in an emergency)
	docker login -u AWS -p $$(aws ecr get-login-password --region us-east-1) $(ECR_URL_STAGE)
	docker push $(ECR_URL_STAGE):latest
	docker push $(ECR_URL_STAGE):`git describe --always`

update-lambda-stage: # Update the Lambda function code with the most recent image on ECR for stage (only use in an emergency)
	aws lambda update-function-code --function-name $(FUNCTION_STAGE) --image-uri $(ECR_URL_STAGE):latest
