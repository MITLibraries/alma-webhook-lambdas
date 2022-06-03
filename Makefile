### This is the Terraform-generated header for the timdex-pipeline-lambads Makefile ###
SHELL=/bin/bash
DATETIME:=$(shell date -u +%Y%m%dT%H%M%SZ)
### This is the Terraform-generated header for alma-webhook-lambdas-dev
ECR_NAME_DEV:=alma-webhook-lambdas-dev
ECR_URL_DEV:=222053980223.dkr.ecr.us-east-1.amazonaws.com/alma-webhook-lambdas-dev
FUNCTION_DEV:=alma-webhook-lambdas-dev
### End of Terraform-generated header ###
### This is the Terraform-generated header for alma-webhook-lambdas-stage
ECR_NAME_STAGE:=alma-webhook-lambdas-stage
ECR_URL_STAGE:=840055183494.dkr.ecr.us-east-1.amazonaws.com/alma-webhook-lambdas-stage
FUNCTION_STAGE:=alma-webhook-lambdas-stage
### End of Terraform-generated header ###

help: ## Print this message
	@awk 'BEGIN { FS = ":.*##"; print "Usage:  make <target>\n\nTargets:" } \
/^[-_[:alpha:]]+:.?*##/ { printf "  %-15s%s\n", $$1, $$2 }' $(MAKEFILE_LIST)

### Dependency commands ###
install: ## Install dependencies
	pipenv install --dev

update: install ## Update all Python dependencies
	pipenv clean
	pipenv update --dev
	pipenv requirements

### Test commands ###
test: ## Run tests and print a coverage report
	pipenv run coverage run --source=lambdas -m pytest
	pipenv run coverage report -m

coveralls: test
	pipenv run coverage lcov -o ./coverage/lcov.info

### Lint commands ###
lint: bandit black flake8 isort mypy ## Lint the repo

bandit:
	pipenv run bandit -r lambdas

black:
	pipenv run black --check --diff .

flake8:
	pipenv run flake8 .

isort:
	pipenv run isort . --diff

mypy:
	pipenv run mypy lambdas

### Developer Deploy Commands ###
dist-dev: ## Build docker container (intended for developer-based manual build)
	docker build --platform linux/amd64 \
	    -t $(ECR_URL_DEV):latest \
		-t $(ECR_URL_DEV):`git describe --always` \
		-t $(ECR_NAME_DEV):latest .

publish-dev: dist-dev ## Build, tag and push (intended for developer-based manual publish)
	docker login -u AWS -p $$(aws ecr get-login-password --region us-east-1) $(ECR_URL_DEV)
	docker push $(ECR_URL_DEV):latest
	docker push $(ECR_URL_DEV):`git describe --always`

update-lambda-dev: ## Updates the lambda with whatever is the most recent image in the ecr (intended for developer-based manual update)
	aws lambda update-function-code \
		--function-name $(FUNCTION_DEV) \
		--image-uri $(ECR_URL_DEV):latest
		
### developer Deploy Commands ###
dist-stage: ## Build docker container (intended for developer-based manual build)
	docker build --platform linux/amd64 \
	    -t $(ECR_URL_STAGE):latest \
		-t $(ECR_URL_STAGE):`git describe --always` \
		-t $(ECR_NAME_STAGE):latest .

publish-stage: dist-stage ## Build, tag and push (intended for developer-based manual publish)
	docker login -u AWS -p $$(aws ecr get-login-password --region us-east-1) $(ECR_URL_STAGE)
	docker push $(ECR_URL_STAGE):latest
	docker push $(ECR_URL_STAGE):`git describe --always`

update-lambda-stage: ## Updates the lambda with whatever is the most recent image in the ecr (intended for developer-based manual update)
	aws lambda update-function-code \
		--function-name $(FUNCTION_STAGE) \
		--image-uri $(ECR_URL_STAGE):latest
