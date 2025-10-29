# Receipts Automation App

A Flask-based web application for automating receipt processing from Excel files. This application provides a dashboard for uploading, managing, and processing receipt files with PostgreSQL database support.

## Features

- **File Upload**: Upload multiple Excel files (.xlsx, .xls, .csv)
- **Dashboard**: Real-time monitoring of receipts and processing jobs
- **Database Management**: PostgreSQL integration with SQLAlchemy ORM
- **Processing Jobs**: Track and manage receipt processing workflows
- **RESTful API**: Complete API for integration with other systems

## Prerequisites

- Python 3.8 or higher
- PostgreSQL 12 or higher
- pip (Python package installer)

## Installation

### 1. Clone or Download the Project

```bash
cd "/Users/rahul/Documents/1 New Apps/mend/Permanent Reciepts"
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Setup PostgreSQL Database

#### Install PostgreSQL (if not already installed)

**macOS (using Homebrew):**
```bash
brew install postgresql
brew services start postgresql
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### Create Database and User

```bash
# Connect to PostgreSQL as superuser
sudo -u postgres psql

# Create database and user
CREATE DATABASE receipts_dev;
CREATE USER receipts_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE receipts_dev TO receipts_user;
\q
```

### 5. Configure Environment Variables

```bash
# Copy the example environment file
cp env.example .env

# Edit .env file with your database credentials
nano .env
```

Update the following variables in `.env`:
```
DEV_DATABASE_URL=postgresql://receipts_user:your_password@localhost:5432/receipts_dev
SECRET_KEY=your-secret-key-here
```

### 6. Initialize Database

```bash
# Run the database initialization script
python init_db.py

# Initialize Flask migrations
flask db init

# Create initial migration
flask db migrate -m "Initial migration"

# Apply migrations
flask db upgrade
```

### 7. Run the Application

```bash
python app.py
```

The application will be available at `http://localhost:5000`

## Project Structure

```
Permanent Reciepts/
├── app.py                 # Main Flask application
├── models.py              # Database models
├── config.py              # Configuration settings
├── init_db.py             # Database initialization script
├── requirements.txt       # Python dependencies
├── env.example            # Environment variables template
├── templates/             # HTML templates
│   └── index.html
├── static/                # Static files
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
├── uploads/               # File upload directory
└── logs/                  # Application logs
```

## API Endpoints

### Health Check
- `GET /api/health` - Check application and database status

### Receipts
- `GET /api/receipts` - Get all receipts
- `POST /api/receipts` - Create new receipt record

### File Upload
- `POST /api/upload` - Upload Excel files

### Processing Jobs
- `GET /api/jobs` - Get all processing jobs
- `POST /api/jobs` - Create new processing job

## Database Models

### Receipt
- `id`: Primary key
- `filename`: Original filename
- `file_path`: Path to uploaded file
- `status`: Processing status (pending, processing, completed, error)
- `total_amount`: Extracted total amount
- `vendor_name`: Extracted vendor name
- `receipt_date`: Extracted receipt date
- `processed_data`: JSON data from processing
- `created_at`, `updated_at`: Timestamps

### ProcessingJob
- `id`: Primary key
- `job_name`: Name of the processing job
- `status`: Job status (pending, running, completed, failed)
- `input_files`: JSON array of input file paths
- `output_files`: JSON array of output file paths
- `job_config`: JSON configuration for the job
- `started_at`, `completed_at`: Job timestamps
- `error_message`: Error details if job failed

## Development

### Running in Development Mode

```bash
export FLASK_ENV=development
export FLASK_DEBUG=1
python app.py
```

### Database Migrations

```bash
# Create a new migration
flask db migrate -m "Description of changes"

# Apply migrations
flask db upgrade

# Rollback last migration
flask db downgrade
```

### Testing

```bash
# Run tests (when test files are added)
python -m pytest tests/
```

## Production Deployment

### Using Gunicorn

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Environment Variables for Production

```bash
export FLASK_ENV=production
export DATABASE_URL=postgresql://user:password@host:port/database
export SECRET_KEY=your-production-secret-key
```

## Troubleshooting

### Common Issues

1. **Database Connection Error**
   - Verify PostgreSQL is running
   - Check database credentials in `.env`
   - Ensure database exists

2. **Permission Errors**
   - Check file permissions for `uploads/` directory
   - Ensure Flask app has write access

3. **Import Errors**
   - Activate virtual environment
   - Install all dependencies: `pip install -r requirements.txt`

### Logs

Check application logs in the `logs/` directory for detailed error information.

## Next Steps

This is the foundation for your receipts automation system. The next steps will involve:

1. Implementing Excel file processing logic
2. Adding receipt data extraction
3. Creating automated workflows
4. Building output file generation
5. Adding advanced processing features

## Support

For issues and questions, check the application logs and ensure all prerequisites are properly installed.
