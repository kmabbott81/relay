#!/bin/bash
# Relay AI - One-Command Full Stack Deployment
# Usage: bash scripts/deploy-all.sh [--local|--railway|--vercel|--full]

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
RAILWAY_TOKEN="${RAILWAY_TOKEN:-}"
VERCEL_TOKEN="${VERCEL_TOKEN:-}"
API_URL="https://relay-production-f2a6.up.railway.app"
WEB_URL="https://relay-beta.vercel.app"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    if [ "$DEPLOY_MODE" == "railway" ] || [ "$DEPLOY_MODE" == "full" ]; then
        if ! command -v railway &> /dev/null; then
            log_error "Railway CLI not found. Install: npm i -g @railway/cli"
            exit 1
        fi
        if [ -z "$RAILWAY_TOKEN" ]; then
            log_warn "RAILWAY_TOKEN not set. Set it before running:"
            echo "  export RAILWAY_TOKEN=your_token_here"
        fi
    fi

    if [ "$DEPLOY_MODE" == "vercel" ] || [ "$DEPLOY_MODE" == "full" ]; then
        if ! command -v vercel &> /dev/null; then
            log_error "Vercel CLI not found. Install: npm i -g vercel"
            exit 1
        fi
    fi

    if ! command -v git &> /dev/null; then
        log_error "Git not found"
        exit 1
    fi

    log_success "Prerequisites OK"
}

build_local() {
    log_info "Building Docker image locally..."

    cd "$PROJECT_ROOT"

    if docker build -t relay-ai:latest -f Dockerfile .; then
        log_success "Docker image built successfully"
    else
        log_error "Docker build failed"
        exit 1
    fi
}

run_migrations() {
    log_info "Running database migrations..."

    cd "$PROJECT_ROOT"

    # Verify database URL is set
    if [ -z "$DATABASE_URL" ]; then
        log_error "DATABASE_URL environment variable not set"
        return 1
    fi

    # Install migration dependencies
    pip install -q alembic psycopg2-binary sqlalchemy || {
        log_error "Failed to install migration dependencies"
        return 1
    }

    # Test database connectivity
    python -c "
import psycopg2
try:
    conn = psycopg2.connect('$DATABASE_URL')
    conn.close()
    print('Database connectivity verified')
except Exception as e:
    print(f'Database connection failed: {e}')
    exit(1)
" || {
        log_error "Cannot connect to database"
        return 1
    }

    # Run migrations
    alembic upgrade head || {
        log_error "Alembic migrations failed"
        return 1
    }

    log_success "Database migrations completed successfully"
    return 0
}

test_local() {
    log_info "Testing Docker image locally..."

    # Run container with health check
    CONTAINER_ID=$(docker run -d -p 8000:8000 \
        -e RELAY_ENV=staging \
        relay-ai:latest)

    log_info "Container started: $CONTAINER_ID"

    # Wait for container to be ready
    sleep 10

    # Test health endpoint
    if curl -f http://localhost:8000/health; then
        log_success "Local API health check passed"
    else
        log_error "Local API health check failed"
        docker stop "$CONTAINER_ID" || true
        exit 1
    fi

    # Clean up
    docker stop "$CONTAINER_ID"
    log_success "Local testing passed"
}

deploy_railway() {
    log_info "Deploying to Railway..."

    cd "$PROJECT_ROOT"

    # Check git status
    if [ -n "$(git status --porcelain)" ]; then
        log_error "Uncommitted changes detected."
        git status --short
        log_info "Please commit changes before deploying:"
        log_info "  git add <files>"
        log_info "  git commit -m 'your message'"
        exit 1
    fi

    log_info "Running database migrations FIRST..."
    if ! run_migrations; then
        log_error "Database migrations failed. Not deploying API."
        exit 1
    fi

    # Push to main (triggers Railway webhook)
    log_info "Pushing to main branch (triggers Railway deployment)..."
    git push origin main

    log_info "Railway deployment triggered via webhook"
    log_info "Check deployment status:"
    echo "  railway logs --follow"

    # Wait for deployment
    log_info "Waiting 60 seconds for Railway to rebuild..."
    sleep 60

    # Test API health
    log_info "Testing API health..."
    for i in {1..30}; do
        if curl -f "$API_URL/health"; then
            log_success "API is healthy at $API_URL"
            return 0
        fi
        echo "Attempt $i/30: Waiting for API..."
        sleep 5
    done

    log_error "API failed to become healthy after deployment"
    exit 1
}

deploy_vercel() {
    log_info "Deploying web app to Vercel..."

    cd "$PROJECT_ROOT/relay_ai/product/web"

    log_info "Installing dependencies..."
    npm ci

    log_info "Building Next.js app..."
    npm run build

    log_info "Deploying to Vercel..."
    vercel --prod \
        --build-env "NEXT_PUBLIC_API_URL=$API_URL"

    log_success "Web app deployed to Vercel"
    log_info "Access dashboard at: $WEB_URL/beta"
}

run_smoke_tests() {
    log_info "Running smoke tests..."

    # Test API health
    log_info "Testing API health endpoint..."
    if curl -f "$API_URL/health" > /dev/null; then
        log_success "API health check passed"
    else
        log_error "API health check failed"
        return 1
    fi

    # Test knowledge API
    log_info "Testing knowledge API endpoint..."
    if curl -f "$API_URL/api/v1/knowledge/health" > /dev/null; then
        log_success "Knowledge API check passed"
    else
        log_warn "Knowledge API check failed (may be starting up)"
    fi

    # Test web app
    log_info "Testing web app..."
    for i in {1..10}; do
        if curl -f "$WEB_URL/beta" > /dev/null; then
            log_success "Web app loads successfully"
            return 0
        fi
        echo "Attempt $i/10: Waiting for web app..."
        sleep 10
    done

    log_error "Web app failed to load"
    return 1
}

show_usage() {
    cat <<EOF
${BLUE}Relay AI - Full Stack Deployment Script${NC}

Usage: bash scripts/deploy-all.sh [MODE]

Modes:
  --local      Build Docker image locally and test it
  --railway    Deploy API to Railway (requires RAILWAY_TOKEN)
  --vercel     Deploy web app to Vercel (requires Vercel CLI auth)
  --full       Full deployment: Railway + Vercel + tests (DEFAULT)
  --smoke      Run smoke tests only
  --help       Show this message

Examples:
  # Full stack deployment (recommended)
  bash scripts/deploy-all.sh --full

  # Deploy to Railway only
  bash scripts/deploy-all.sh --railway

  # Test locally
  bash scripts/deploy-all.sh --local

Environment Variables:
  RAILWAY_TOKEN     Railway API token (for --railway mode)
  VERCEL_TOKEN      Vercel API token (for --vercel mode)

Dependencies:
  - docker          For local Docker builds
  - git             For Git operations
  - railway         For Railway deployment (npm i -g @railway/cli)
  - vercel          For Vercel deployment (npm i -g vercel)

${YELLOW}First Time Setup:${NC}
  1. Install tools: npm i -g @railway/cli vercel
  2. Authenticate: railway login && vercel login
  3. Set RAILWAY_TOKEN: export RAILWAY_TOKEN=\$(railway token)
  4. Run: bash scripts/deploy-all.sh --full
EOF
}

# Parse arguments
DEPLOY_MODE="full"
if [ $# -gt 0 ]; then
    case "$1" in
        --local)
            DEPLOY_MODE="local"
            ;;
        --railway)
            DEPLOY_MODE="railway"
            ;;
        --vercel)
            DEPLOY_MODE="vercel"
            ;;
        --full)
            DEPLOY_MODE="full"
            ;;
        --smoke)
            DEPLOY_MODE="smoke"
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
fi

# Main execution
log_info "Starting Relay AI deployment (mode: $DEPLOY_MODE)..."

case "$DEPLOY_MODE" in
    local)
        check_prerequisites
        build_local
        test_local
        log_success "Local build and test completed!"
        ;;
    railway)
        check_prerequisites
        deploy_railway
        log_success "Railway deployment completed!"
        ;;
    vercel)
        check_prerequisites
        deploy_vercel
        run_smoke_tests
        log_success "Vercel deployment completed!"
        ;;
    full)
        check_prerequisites
        deploy_railway
        deploy_vercel
        run_smoke_tests
        log_success "Full stack deployment completed!"
        log_info "API: $API_URL"
        log_info "Web: $WEB_URL/beta"
        ;;
    smoke)
        run_smoke_tests
        log_success "Smoke tests passed!"
        ;;
esac

log_success "Deployment script completed"
