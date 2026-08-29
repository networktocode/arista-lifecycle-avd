.PHONY: help dc1-build dc1-deploy dc1-deploy_digital_twin_clab dc1-validate dc1-validate_digital_twin_clab deploy_clab_topology

INVENTORY := sites/DC1/inventory.yml
TARGET := -e 'target=DC1'

help: ## Show the targets
	@grep -E '^[0-9a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-32s\033[0m %s\n", $$1, $$2}'

dc1-build: ## Build DC1 intended configs, documentation, twin artifacts, and the amplification report
	ansible-playbook playbooks/build.yml -i $(INVENTORY) $(TARGET)

dc1-deploy: ## Deploy DC1 to production through CloudVision (CVAAS_SERVER, CVAAS_TOKEN)
	ansible-playbook playbooks/deploy.yml -i $(INVENTORY) $(TARGET)

dc1-deploy_digital_twin_clab: ## Deploy DC1 to the clab digital twin through CloudVision
	ansible-playbook playbooks/deploy_digital_twin_clab.yml -i $(INVENTORY) $(TARGET)

dc1-validate: ## Run ANTA against production DC1 (ANTA_USERNAME, ANTA_PASSWORD)
	ansible-playbook playbooks/validate.yml -i $(INVENTORY) --diff $(TARGET)

dc1-validate_digital_twin_clab: ## Run ANTA against the clab digital twin
	ansible-playbook playbooks/validate_digital_twin_clab.yml -i $(INVENTORY) --diff $(TARGET)

deploy_clab_topology: ## Start the twin topology with containerlab (on the clab host)
	clab deploy -t digital_twin/clab/topology.clab.yml
