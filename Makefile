.PHONY: help install init-db prepare-standards worker-std stats reset-failed cleanup export docker-build docker-up docker-down full-cycle

# Default target
help:
	@echo "Available commands:"
	@echo "  make install              - Install dependencies"
	@echo "  make init-db              - Initialize standardized database"
	@echo "  make prepare-standards    - Prepare OKPD2 standards file"
	@echo "  make validate-standards   - Validate OKPD2 standards file"
	@echo ""
	@echo "Worker commands:"
	@echo "  make worker-std           - Run standardization worker"
	@echo "  make worker-std-2         - Run second standardization worker"
	@echo "  make worker-std-3         - Run third standardization worker"
	@echo "  make workers-all          - Run all 3 workers (Tier 2)"
	@echo ""
	@echo "Monitoring:"
	@echo "  make stats                - Show standardization statistics"
	@echo "  make monitor              - Live monitoring (basic)"
	@echo "  make monitor-perf         - Live performance monitoring with speed"
	@echo ""
	@echo "Data management:"
	@echo "  make reset-failed         - Reset failed products to pending"
	@echo "  make cleanup              - Clean up stuck products"
	@echo "  make export               - Export sample standardized data (JSON)"
	@echo "  make export-excel         - Export all standardized products to Excel"
	@echo "  make export-excel-filtered OKPD=XX - Export filtered products to Excel"
	@echo "  make analyze              - Analyze standardization results"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build         - Build Docker images"
	@echo "  make docker-up            - Start services in Docker"
	@echo "  make docker-down          - Stop Docker services"
	@echo ""
	@echo "Quick start:"
	@echo "  make full-cycle API_KEY=your-key - Run full standardization cycle"

# Install dependencies
install:
	pip install -r requirements.txt

# Initialize standardized database
init-db:
	@echo "Initializing standardized database..."
	@python -c "import asyncio; from src.storage.standardized_mongo import StandardizedMongoStore; from src.core.config import settings; \
		async def init(): \
			store = StandardizedMongoStore(settings.standardized_mongodb_database); \
			await store.initialize(); \
			print('Database initialized successfully'); \
			await store.close(); \
		asyncio.run(init())"

# Prepare standards file (if needed)
prepare-standards:
	@echo "Checking OKPD2 standards file..."
	@if [ ! -f "src/data/okpd2_characteristics.json" ]; then \
		echo "ERROR: Standards file not found!"; \
		echo "Please create src/data/okpd2_characteristics.json with OKPD2 standards"; \
		exit 1; \
	else \
		echo "Standards file found"; \
		python -c "import json; \
			with open('src/data/okpd2_characteristics.json', 'r') as f: \
				data = json.load(f); \
				groups = data.get('okpd2_characteristics', {}); \
				print(f'Loaded standards for {len(groups)} OKPD2 groups'); \
				for g in sorted(groups.keys()): \
					chars = groups[g].get('characteristics', {}); \
					print(f'  Group {g}: {len(chars)} characteristics')"; \
	fi

# Validate standards file
validate-standards:
	@python scripts/validate_standards.py

# Run standardization worker
worker-std:
	python -m src.workers.standardization_worker --worker-id std_worker_1

# Run second worker
worker-std-2:
	python -m src.workers.standardization_worker --worker-id std_worker_2 --log-level INFO

# Run third worker
worker-std-3:
	python -m src.workers.standardization_worker --worker-id std_worker_3 --log-level INFO

# Run all 3 workers (для Tier 2)
workers-all:
	@echo "Starting 3 workers for Tier 2 parallel processing..."
	@echo "Press Ctrl+C to stop all workers"
	@parallel --ungroup ::: \
		"python -m src.workers.standardization_worker --worker-id std_worker_1" \
		"python -m src.workers.standardization_worker --worker-id std_worker_2" \
		"python -m src.workers.standardization_worker --worker-id std_worker_3"

# Show statistics
stats:
	@curl -s -X GET \
		"http://localhost:8000/api/v1/standardization/stats" \
		-H "X-API-Key: $(API_KEY)" | python -m json.tool

# Monitor statistics continuously
monitor:
	@while true; do \
		clear; \
		echo "=== STANDARDIZATION STATISTICS ==="; \
		echo "Time: $(date)"; \
		echo ""; \
		curl -s -X GET \
			"http://localhost:8000/api/v1/standardization/stats" \
			-H "X-API-Key: $(API_KEY)" | python -m json.tool; \
		sleep 5; \
	done

# Performance monitoring with speed calculations
monitor-perf:
	@python scripts/monitor_performance.py

# Reset failed products
reset-failed:
	@curl -X POST \
		"http://localhost:8000/api/v1/standardization/reset-failed" \
		-H "X-API-Key: $(API_KEY)" | python -m json.tool

# Clean up stuck products
cleanup:
	@curl -X POST \
		"http://localhost:8000/api/v1/standardization/cleanup-stuck" \
		-H "X-API-Key: $(API_KEY)" | python -m json.tool

# Export sample data
export:
	@curl -s -X GET \
		"http://localhost:8000/api/v1/standardization/export/sample?limit=20" \
		-H "X-API-Key: $(API_KEY)" | python -m json.tool > standardized_sample_$(date +%Y%m%d_%H%M%S).json
	@echo "Exported to standardized_sample_$(date +%Y%m%d_%H%M%S).json"

# Export to Excel
export-excel:
	@echo "Exporting standardized products to Excel..."
	@python scripts/export_to_excel.py

# Export filtered data to Excel
export-excel-filtered:
	@if [ -z "$(OKPD)" ]; then \
		echo "Usage: make export-excel-filtered OKPD=17"; \
	else \
		python scripts/export_to_excel.py -f $(OKPD) -o standardized_okpd$(OKPD)_$(date +%Y%m%d_%H%M%S).xlsx; \
	fi

# Analyze standardization results
analyze:
	@python scripts/analyze_results.py

# Get attributes summary
attributes:
	@curl -s -X GET \
		"http://localhost:8000/api/v1/standardization/attributes/summary" \
		-H "X-API-Key: $(API_KEY)" | python -m json.tool

# Search by attribute
search-attr:
	@if [ -z "$(ATTR)" ]; then \
		echo "Usage: make search-attr ATTR=attribute_name [VALUE=attribute_value]"; \
	else \
		curl -s -X GET \
			"http://localhost:8000/api/v1/standardization/products/standardized?attribute_name=$(ATTR)&attribute_value=$(VALUE)&limit=10" \
			-H "X-API-Key: $(API_KEY)" | python -m json.tool; \
	fi

# Docker commands
docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f standardization-worker

# Full cycle
full-cycle: prepare-standards validate-standards init-db
	@echo "Starting full standardization cycle..."
	@echo "1. Checking prerequisites..."
	@make stats API_KEY=$(API_KEY) || (echo "API not running. Please start it first"; exit 1)
	@echo ""
	@echo "2. Starting standardization worker..."
	@echo "Press Ctrl+C to stop"
	@make worker-std

# Development helpers
dev-api:
	uvicorn src.main:app --reload --port 8000

dev-worker:
	python -m src.workers.standardization_worker --worker-id dev_worker --log-level DEBUG

# Database helpers
db-shell:
	mongosh mongodb://localhost:27017/standardized_products

db-check-classified:
	@echo "Checking classified products ready for standardization..."
	@mongosh mongodb://localhost:27017/okpd_classifier --quiet --eval \
		'db.products_classifier.countDocuments({status_stg2: "classified", standardization_status: {$$ne: "standardized"}})'

db-check-standardized:
	@echo "Checking standardized products..."
	@mongosh mongodb://localhost:27017/standardized_products --quiet --eval \
		'db.standardized_products.countDocuments({})'