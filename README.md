# Solar Monitor

A comprehensive solar plant monitoring system built with Django, Celery, and Apache Airflow, designed for tracking solar energy production, battery levels, and grid exports. The system supports automated report generation and can be deployed on Kubernetes for scalable operations.

## Features

- **Plant Management**: Register and manage multiple solar plants with capacity tracking
- **Real-time Monitoring**: Record and track solar readings (power output, battery percentage, grid exports)
- **Automated Reports**: Generate daily, weekly, and monthly CSV reports via Airflow scheduling
- **Pipeline Processing**: Simulate and track data processing pipelines
- **Asynchronous Tasks**: Celery-based task processing for performance
- **Kubernetes Deployment**: Containerized deployment with K8s manifests
- **Metrics and Monitoring**: Prometheus integration for system metrics

## Architecture

The system consists of:
- **Django Backend**: Web interface and API for plant management, readings, and reports
- **Celery Workers**: Asynchronous task processing for data imports and computations
- **Airflow**: Workflow orchestration for scheduled reports and pipeline execution
- **PostgreSQL**: Primary database for application data
- **Kubernetes**: Container orchestration for production deployment

## Data Model

### Solar Plants
- Name, location, capacity (kW)
- Owner association

### Solar Readings
- Timestamp, power output (kW), battery percentage, grid export (kW)
- Unique constraint on plant + timestamp

### Reports
- Automated CSV generation for daily/weekly/monthly periods
- Stored in `reports_output/` directory

## Setup

### Prerequisites
- Python 3.11+
- Docker and Docker Compose
- kubectl (for Kubernetes deployment)
- Kind (for local Kubernetes cluster)
- PostgreSQL (or use Docker)

### Local Development Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd solar_monitor
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Database setup**
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

5. **Load sample data** (optional)
   ```bash
   python manage.py shell -c "
   from plants.models import SolarPlant
   from django.contrib.auth.models import User
   user = User.objects.create_superuser('admin', 'admin@example.com', 'password')
   plant = SolarPlant.objects.create(name='Demo Plant', location='Test Location', capacity_kw=10.0, owner=user)
   "
   ```

6. **Start Django server**
   ```bash
   python manage.py runserver
   ```

7. **Start Celery worker** (in another terminal)
   ```bash
   celery -A solar_monitor worker --loglevel=info
   ```

### Airflow Setup

1. **Using Docker Compose**
   ```bash
   docker-compose -f docker-compose.airflow.yml up --build
   ```

2. **Access Airflow UI**
   - URL: http://localhost:8081
   - Username: admin
   - Password: admin

3. **Environment Variables for Airflow**
   Set these in your environment or docker-compose:
   ```bash
   export DJANGO_BASE_URL=http://host.docker.internal:8000
   export AIRFLOW_REPORTS_TOKEN=your-token-here
   export PIPELINE_OWNER_ID=1
   export REPORT_OWNER_ID=1
   ```

## Usage

### Django Web Interface
- Access at http://localhost:8000/admin for admin interface
- API endpoints available under `/api/`

### Data Import
Upload CSV files with readings data. Format:
```csv
timestamp,power_kw,battery_percentage,grid_export_kw
2026-03-03T06:00:00,0.5,50.0,0.0
2026-03-03T07:00:00,2.5,55.0,0.5
...
```

### Airflow DAGs
- `solar_demo_pipeline_tracking`: Demonstrates pipeline execution
- `solar_scheduled_reports`: Generates periodic reports
- `k8s_simulate_readings`: Simulates readings data

### Commands

#### Django Management
```bash
# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run tests
python manage.py test

# Collect static files
python manage.py collectstatic
```

#### Celery
```bash
# Start worker
celery -A solar_monitor worker --loglevel=info

# Start beat scheduler
celery -A solar_monitor beat --loglevel=info
```

#### Docker
```bash
# Build and run Airflow
docker-compose -f docker-compose.airflow.yml up --build

# Run in background
docker-compose -f docker-compose.airflow.yml up -d

# Stop services
docker-compose -f docker-compose.airflow.yml down
```

#### Kubernetes Deployment
```bash
# Apply Kubernetes manifests
kubectl apply -f k8s/airflow/

# Check pods
kubectl get pods -n airflow

# View logs
kubectl logs -n airflow <pod-name>
```

## Configuration

### Environment Variables
- `DJANGO_SETTINGS_MODULE`: Django settings module
- `DJANGO_BASE_URL`: Base URL for Django API (used by Airflow)
- `AIRFLOW_REPORTS_TOKEN`: Authentication token for Airflow-Django communication
- `PIPELINE_OWNER_ID`: Default owner ID for pipelines
- `REPORT_OWNER_ID`: Default owner ID for reports

### Database
Default: SQLite (db.sqlite3)
For production, configure PostgreSQL in settings.py

### Airflow Configuration
- Executor: LocalExecutor (can be changed to KubernetesExecutor)
- Database: PostgreSQL via docker-compose
- DAGs location: `airflow/dags/`

## Data

### Sample Data
- `sample_readings.csv`: Example solar readings data
- `test-dlv.csv`: Test data for development

### Report Outputs
Generated reports are stored in `reports_output/` with naming convention:
`report_{period}_all_plants_owner_{id}_{timestamp}.csv`

## Development

### Project Structure
```
solar_monitor/
├── solar_monitor/          # Django project settings
├── plants/                 # Solar plant management app
├── reports/                # Report generation app
├── airflow/                # Airflow DAGs and config
│   └── dags/              # DAG definitions
├── k8s/                   # Kubernetes manifests
├── templates/             # Django templates
├── reports_output/        # Generated report files
└── requirements.txt       # Python dependencies
```

### Testing
```bash
python manage.py test plants reports
```

### Code Quality
- Use Black for code formatting
- Run flake8 for linting
- Add type hints where possible

## Deployment

### Docker
```bash
# Build image
docker build -t solar-monitor .

# Run container
docker run -p 8000:8000 solar-monitor
```

### Kubernetes
1. Apply namespace and RBAC:
   ```bash
   kubectl apply -f k8s/airflow/01-namespace-rbac.yaml
   ```

2. Deploy Airflow:
   ```bash
   kubectl apply -f k8s/airflow/02-airflow-deployment.yaml
   ```

3. Configure ingress and services as needed

### Kind Cluster Setup
For local development with Kind (Kubernetes in Docker):

1. **Create Kind cluster**:
   ```bash
   kind create cluster --name airflow-k8s
   ```

2. **Create namespace**:
   ```bash
   kubectl create namespace airflow
   ```

3. **Build Docker image**:
   ```bash
   docker build -t solar-monitor-airflow:latest .
   ```

4. **Load image into Kind**:
   ```bash
   kind load docker-image solar-monitor-airflow:latest --name airflow-k8s
   ```

5. **Stop local Docker Compose** (if running):
   ```bash
   docker compose -f docker-compose.airflow.yml --env-file .env down
   ```

6. **Start Docker Compose**:
   ```bash
   docker compose -f docker-compose.airflow.yml --env-file .env up
   ```

   Note: The internal IP of the Kind control-plane is 172.20.0.2.

7. **Run Django server**:
   ```bash
   source venv/bin/activate
   export $(grep -v '^#' .env | xargs)
   AIRFLOW_REPORTS_TOKEN="$AIRFLOW_REPORTS_TOKEN" python3 manage.py runserver 0.0.0.0:8000
   ```

8. **Port forward services**:
   ```bash
   kubectl port-forward -n airflow svc/airflow-webserver 8082:8080
   kubectl port-forward -n airflow svc/postgres 5433:5432
   ```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## License

[Add license information here]
