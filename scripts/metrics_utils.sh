#!/bin/bash

################################################################################
#
# Metrics Utilities for Deployment Pipeline
#
# Provides functions to record deployment metrics to Prometheus Pushgateway
# Usage in deployment scripts:
#
#   source scripts/metrics_utils.sh
#   export DEPLOYMENT_ID="$GITHUB_RUN_ID"
#   export ENVIRONMENT="production"
#
#   record_stage "build" "api" "success" "95.4"
#   record_health_check "42" "healthy"
#   record_deployment_complete "450.2"
#
################################################################################

set -e

# ============================================================================
# CONFIGURATION
# ============================================================================

# Prometheus Pushgateway URL
PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://localhost:9091}"

# Deployment metadata
DEPLOYMENT_ID="${DEPLOYMENT_ID:-$(date +%s)}"
ENVIRONMENT="${ENVIRONMENT:-production}"
BRANCH="${BRANCH:-unknown}"
TRIGGERED_BY="${TRIGGERED_BY:-manual}"

# Colors for console output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================================
# INTERNAL HELPERS
# ============================================================================

# Print colored info message
_log_info() {
    echo -e "${BLUE}[METRICS]${NC} $1"
}

# Print colored success message
_log_success() {
    echo -e "${GREEN}[METRICS]${NC} $1"
}

# Print colored warning message
_log_warn() {
    echo -e "${YELLOW}[METRICS]${NC} $1"
}

# Print colored error message
_log_error() {
    echo -e "${RED}[METRICS]${NC} $1"
}

# Push metrics to Prometheus Pushgateway
# Internal function - uses curl to push metrics
_push_metrics() {
    local metrics_data="$1"
    local job_name="deployment-pipeline"
    local instance="${DEPLOYMENT_ID}"

    if [ -z "$PUSHGATEWAY_URL" ] || [ "$PUSHGATEWAY_URL" = "disabled" ]; then
        _log_warn "Pushgateway disabled, skipping push"
        return 0
    fi

    # Attempt push with retry logic
    local max_attempts=3
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if echo -e "$metrics_data" | curl -s --data-binary @- \
            "${PUSHGATEWAY_URL}/metrics/job/${job_name}/instance/${instance}" \
            2>/dev/null; then
            return 0
        fi

        if [ $attempt -lt $max_attempts ]; then
            _log_warn "Push attempt $attempt/$max_attempts failed, retrying..."
            sleep 1
        fi

        ((attempt++))
    done

    _log_warn "Failed to push metrics after $max_attempts attempts"
    return 1
}

# ============================================================================
# PUBLIC METRICS FUNCTIONS
# ============================================================================

# Record stage start time for automatic duration calculation
# Usage: record_stage_start "build" "api"
record_stage_start() {
    local stage="$1"
    local service="$2"

    # Store start time for later duration calculation
    export "STAGE_START_${stage}_${service}=$(date +%s%N | cut -b1-13)"
    _log_info "Stage started: $stage ($service)"
}

# Record stage completion with metrics
# Usage: record_stage "build" "api" "success" "95.4"
# or: record_stage "build" "api" "failure" "120" "timeout"
record_stage() {
    local stage="$1"
    local service="$2"
    local status="$3"
    local duration="${4:-0}"
    local error_type="${5:-}"

    # Validate inputs
    if [ -z "$stage" ] || [ -z "$service" ] || [ -z "$status" ]; then
        _log_error "record_stage: missing required arguments"
        return 1
    fi

    # Calculate duration from start time if not provided
    if [ "$duration" = "0" ] || [ -z "$duration" ]; then
        local start_time_var="STAGE_START_${stage}_${service}"
        local start_time="${!start_time_var:-}"

        if [ -n "$start_time" ]; then
            local end_time=$(date +%s%N | cut -b1-13)
            duration=$(echo "scale=3; ($end_time - $start_time) / 1000" | bc)
        fi
    fi

    # Build Prometheus metric
    local metric_labels="stage=\"${stage}\",service=\"${service}\",status=\"${status}\",environment=\"${ENVIRONMENT}\",deployment_id=\"${DEPLOYMENT_ID}\""
    local metrics="# HELP deployment_stage_duration_seconds Deployment stage duration
# TYPE deployment_stage_duration_seconds gauge
deployment_stage_duration_seconds{${metric_labels}} ${duration}"

    # If error, also record error counter
    if [ "$status" = "failure" ] && [ -n "$error_type" ]; then
        metrics="${metrics}
# HELP deployment_errors_total Deployment errors
# TYPE deployment_errors_total counter
deployment_errors_total{stage=\"${stage}\",service=\"${service}\",error_type=\"${error_type}\",environment=\"${ENVIRONMENT}\",deployment_id=\"${DEPLOYMENT_ID}\"} 1"
    fi

    # Push to gateway
    if _push_metrics "$metrics"; then
        if [ -n "$error_type" ]; then
            _log_error "Stage: $stage ($service) - $status ($duration s) - Error: $error_type"
        else
            _log_success "Stage: $stage ($service) - $status ($duration s)"
        fi
    else
        _log_warn "Failed to push stage metrics for $stage"
    fi

    return 0
}

# Record health check result
# Usage: record_health_check "42" "healthy"
# Usage: record_health_check "5000" "unhealthy"
record_health_check() {
    local latency_ms="${1:-0}"
    local status="${2:-unknown}"
    local endpoint="${3:-/health}"

    if [ -z "$latency_ms" ] || [ -z "$status" ]; then
        _log_error "record_health_check: missing required arguments"
        return 1
    fi

    local metric_labels="status=\"${status}\",environment=\"${ENVIRONMENT}\",deployment_id=\"${DEPLOYMENT_ID}\",endpoint=\"${endpoint}\""
    local metrics="# HELP api_health_check_latency_ms Health check latency in milliseconds
# TYPE api_health_check_latency_ms gauge
api_health_check_latency_ms{${metric_labels}} ${latency_ms}"

    if _push_metrics "$metrics"; then
        if [ "$status" = "healthy" ]; then
            _log_success "Health check: $status ($latency_ms ms) - $endpoint"
        else
            _log_warn "Health check: $status ($latency_ms ms) - $endpoint"
        fi
    else
        _log_warn "Failed to push health check metrics"
    fi

    return 0
}

# Record database migration completion
# Usage: record_migration "v001_initial" "production" "45.2" "success" "1"
record_migration() {
    local migration_name="${1:-unknown}"
    local environment="${2:-$ENVIRONMENT}"
    local duration="${3:-0}"
    local status="${4:-success}"
    local migration_count="${5:-1}"

    if [ -z "$migration_name" ]; then
        _log_error "record_migration: missing migration_name"
        return 1
    fi

    local metric_labels="environment=\"${environment}\",deployment_id=\"${DEPLOYMENT_ID}\",migration_name=\"${migration_name}\",status=\"${status}\""
    local count_labels="environment=\"${environment}\",deployment_id=\"${DEPLOYMENT_ID}\",migration_count=\"${migration_count}\""

    local metrics="# HELP migration_total Total database migrations
# TYPE migration_total counter
migration_total{${metric_labels}} 1
# HELP database_migration_lag_seconds Migration duration in seconds
# TYPE database_migration_lag_seconds gauge
database_migration_lag_seconds{${count_labels}} ${duration}"

    if _push_metrics "$metrics"; then
        _log_success "Migration: $migration_name - $status (${duration}s)"
    else
        _log_warn "Failed to push migration metrics"
    fi

    return 0
}

# Record smoke test result
# Usage: record_smoke_test "health_check" "success"
# Usage: record_smoke_test "knowledge_api" "failure" "API returned 500"
record_smoke_test() {
    local test_name="${1:-unknown}"
    local status="${2:-unknown}"
    local error_msg="${3:-}"

    if [ -z "$test_name" ] || [ -z "$status" ]; then
        _log_error "record_smoke_test: missing required arguments"
        return 1
    fi

    local metric_labels="test_name=\"${test_name}\",status=\"${status}\",environment=\"${ENVIRONMENT}\",deployment_id=\"${DEPLOYMENT_ID}\""
    local metrics="# HELP smoke_test_total Smoke tests executed
# TYPE smoke_test_total counter
smoke_test_total{${metric_labels}} 1"

    if _push_metrics "$metrics"; then
        if [ "$status" = "success" ]; then
            _log_success "Smoke test: $test_name - $status"
        else
            _log_warn "Smoke test: $test_name - $status"
            if [ -n "$error_msg" ]; then
                _log_error "  Error: $error_msg"
            fi
        fi
    else
        _log_warn "Failed to push smoke test metrics"
    fi

    return 0
}

# Record deployment start
# Usage: record_deployment_start "main"
record_deployment_start() {
    local branch="${1:-$BRANCH}"

    if [ -z "$branch" ]; then
        branch="unknown"
    fi

    local metric_labels="environment=\"${ENVIRONMENT}\",deployment_id=\"${DEPLOYMENT_ID}\",branch=\"${branch}\",triggered_by=\"${TRIGGERED_BY}\""
    local metrics="# HELP deployment_in_progress Whether deployment is in progress
# TYPE deployment_in_progress gauge
deployment_in_progress{${metric_labels}} 1"

    if _push_metrics "$metrics"; then
        _log_success "Deployment started: $DEPLOYMENT_ID on $branch"
    else
        _log_warn "Failed to push deployment start metrics"
    fi

    return 0
}

# Record deployment completion
# Usage: record_deployment_complete "456.2"
record_deployment_complete() {
    local total_duration="${1:-0}"
    local success="${2:-true}"

    if [ -z "$total_duration" ]; then
        _log_error "record_deployment_complete: missing total_duration"
        return 1
    fi

    local branch="${BRANCH:-unknown}"
    local in_progress_labels="environment=\"${ENVIRONMENT}\",deployment_id=\"${DEPLOYMENT_ID}\",branch=\"${branch}\",triggered_by=\"${TRIGGERED_BY}\""
    local ttd_labels="environment=\"${ENVIRONMENT}\""

    local metrics="# HELP deployment_in_progress Whether deployment is in progress
# TYPE deployment_in_progress gauge
deployment_in_progress{${in_progress_labels}} 0
# HELP time_to_deploy_seconds Total time to deploy
# TYPE time_to_deploy_seconds histogram
time_to_deploy_seconds_bucket{le=\"60\",${ttd_labels}} 0
time_to_deploy_seconds_bucket{le=\"300\",${ttd_labels}} 0
time_to_deploy_seconds_bucket{le=\"600\",${ttd_labels}} 0
time_to_deploy_seconds_bucket{le=\"900\",${ttd_labels}} 0
time_to_deploy_seconds_bucket{le=\"1200\",${ttd_labels}} 0
time_to_deploy_seconds_bucket{le=\"1500\",${ttd_labels}} 0
time_to_deploy_seconds_bucket{le=\"1800\",${ttd_labels}} 1
time_to_deploy_seconds_bucket{le=\"+Inf\",${ttd_labels}} 1
time_to_deploy_seconds_sum{${ttd_labels}} ${total_duration}
time_to_deploy_seconds_count{${ttd_labels}} 1"

    if _push_metrics "$metrics"; then
        if [ "$success" = "true" ]; then
            _log_success "Deployment complete: $total_duration seconds"
        else
            _log_error "Deployment failed after $total_duration seconds"
        fi
    else
        _log_warn "Failed to push deployment complete metrics"
    fi

    return 0
}

# Record rollback event
# Usage: record_rollback "health_check_failed" "success"
# Usage: record_rollback "manual" "failure"
record_rollback() {
    local reason="${1:-unknown}"
    local status="${2:-unknown}"
    local duration="${3:-0}"

    if [ -z "$reason" ] || [ -z "$status" ]; then
        _log_error "record_rollback: missing required arguments"
        return 1
    fi

    local metric_labels="deployment_id=\"${DEPLOYMENT_ID}\",reason=\"${reason}\",status=\"${status}\",environment=\"${ENVIRONMENT}\""
    local metrics="# HELP deployment_rollback_total Deployment rollbacks
# TYPE deployment_rollback_total counter
deployment_rollback_total{${metric_labels}} 1"

    if _push_metrics "$metrics"; then
        if [ "$status" = "success" ]; then
            _log_success "Rollback executed: $reason ($duration s)"
        else
            _log_error "Rollback failed: $reason"
        fi
    else
        _log_warn "Failed to push rollback metrics"
    fi

    return 0
}

# Record post-deployment error rate
# Usage: record_post_deployment_error_rate "0.035" "api"
record_post_deployment_error_rate() {
    local error_rate="${1:-0}"
    local service="${2:-api}"

    if [ -z "$error_rate" ]; then
        _log_error "record_post_deployment_error_rate: missing error_rate"
        return 1
    fi

    local metric_labels="environment=\"${ENVIRONMENT}\",deployment_id=\"${DEPLOYMENT_ID}\",service=\"${service}\""
    local metrics="# HELP post_deployment_error_rate Error rate after deployment
# TYPE post_deployment_error_rate gauge
post_deployment_error_rate{${metric_labels}} ${error_rate}"

    if _push_metrics "$metrics"; then
        local error_percent=$(echo "scale=2; $error_rate * 100" | bc)
        if (( $(echo "$error_rate > 0.05" | bc -l) )); then
            _log_error "Post-deployment error rate: ${error_percent}% (HIGH)"
        elif (( $(echo "$error_rate > 0.01" | bc -l) )); then
            _log_warn "Post-deployment error rate: ${error_percent}%"
        else
            _log_success "Post-deployment error rate: ${error_percent}%"
        fi
    else
        _log_warn "Failed to push error rate metrics"
    fi

    return 0
}

# Record infrastructure cost for deployment
# Usage: record_infrastructure_cost "railway_compute" "2.50"
record_infrastructure_cost() {
    local resource="${1:-unknown}"
    local cost_usd="${2:-0}"

    if [ -z "$resource" ] || [ -z "$cost_usd" ]; then
        _log_error "record_infrastructure_cost: missing required arguments"
        return 1
    fi

    local metric_labels="environment=\"${ENVIRONMENT}\",deployment_id=\"${DEPLOYMENT_ID}\",resource=\"${resource}\""
    local metrics="# HELP deployment_infrastructure_cost Deployment infrastructure cost
# TYPE deployment_infrastructure_cost gauge
deployment_infrastructure_cost{${metric_labels}} ${cost_usd}"

    if _push_metrics "$metrics"; then
        _log_info "Infrastructure cost: $resource = \$$cost_usd"
    else
        _log_warn "Failed to push cost metrics"
    fi

    return 0
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

# Show configuration for debugging
show_metrics_config() {
    echo ""
    echo "Metrics Configuration:"
    echo "  Pushgateway URL:  $PUSHGATEWAY_URL"
    echo "  Deployment ID:    $DEPLOYMENT_ID"
    echo "  Environment:      $ENVIRONMENT"
    echo "  Branch:           $BRANCH"
    echo "  Triggered By:     $TRIGGERED_BY"
    echo ""
}

# Validate configuration
validate_metrics_config() {
    if [ -z "$DEPLOYMENT_ID" ]; then
        _log_error "DEPLOYMENT_ID not set"
        return 1
    fi

    if [ -z "$ENVIRONMENT" ]; then
        _log_error "ENVIRONMENT not set"
        return 1
    fi

    if [ "$PUSHGATEWAY_URL" = "disabled" ]; then
        _log_warn "Metrics collection disabled"
        return 0
    fi

    if ! command -v curl &> /dev/null; then
        _log_error "curl not found (required for metrics)"
        return 1
    fi

    return 0
}

# ============================================================================
# EXPORTED FUNCTIONS
# ============================================================================

export -f record_stage
export -f record_stage_start
export -f record_health_check
export -f record_migration
export -f record_smoke_test
export -f record_deployment_start
export -f record_deployment_complete
export -f record_rollback
export -f record_post_deployment_error_rate
export -f record_infrastructure_cost
export -f show_metrics_config
export -f validate_metrics_config

# ============================================================================
# INITIALIZATION
# ============================================================================

# Validate config on script load
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    # Script was executed directly
    validate_metrics_config
    show_metrics_config
else
    # Script was sourced
    if validate_metrics_config; then
        _log_info "Metrics utilities loaded successfully"
    fi
fi
