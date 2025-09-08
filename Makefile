SHELL := /bin/bash

deploy:
	@echo "Deploying from branch: $$(git rev-parse --abbrev-ref HEAD) by $$(git config user.name) at $$(date '+%Y-%m-%d %H:%M:%S')" > deployer
	rsync -avhzL --delete \
		--no-perms --no-owner --no-group \
		--exclude .git \
		--exclude .env \
		--exclude .env.dev \
		--exclude dist \
		--exclude .venv \
		--exclude node_modules \
		--include deployer \
		--filter=":- .gitignore" \
		. sotatek@192.168.200.23:~/crawl-VPTW
	ssh -t sotatek@192.168.200.23 "cd ./crawl-VPTW ; bash --login"

deploy-preprod:
	@echo "Deploying from branch: $$(git rev-parse --abbrev-ref HEAD) by $$(git config user.name) at $$(date '+%Y-%m-%d %H:%M:%S')" > deployer
	rsync -avhzL --delete \
		--no-perms --no-owner --no-group \
		--exclude .git \
		--exclude .env \
		--exclude .env.dev \
		--exclude dist \
		--exclude .venv \
		--exclude node_modules \
		--include deployer \
		--filter=":- .gitignore" \
		. notex@192.168.200.21:/home/sotatek/sotaagents/crawl-VPTW
	ssh -t notex@192.168.200.21 "cd /home/sotatek/sotaagents/crawl-VPTW ; bash --login"

start:
	pm2 start ecosystem.config.js

stop:
	pm2 stop crawl.vptw

delete:
	pm2 delete crawl.vptw