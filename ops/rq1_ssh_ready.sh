#!/usr/bin/env bash
# Source this helper before a VM operation. Retry only the harmless SSH probe.
rq1_wait_for_ssh() {
    local rq1_host=$1 rq1_identity=$2 rq1_error_log=$3
    local rq1_probe rq1_probe_exit
    for ((rq1_probe = 1; rq1_probe <= 12; rq1_probe++)); do
        printf 'Checking SSH readiness (%s/12); no experiment is running in this check.\n' "$rq1_probe"
        if LC_ALL=C ssh -n -i "$rq1_identity" \
                -o ConnectTimeout=5 -o ConnectionAttempts=1 \
                -o ServerAliveInterval=5 -o ServerAliveCountMax=1 \
                "rq1@$rq1_host" true 2> "$rq1_error_log"; then
            echo 'SSH is ready.'
            return 0
        else
            rq1_probe_exit=$?
        fi
        cat "$rq1_error_log" >&2
        if [[ "$rq1_probe_exit" -ne 255 ]] ||
                LC_ALL=C grep -Eiq 'Permission denied|Host key verification failed|REMOTE HOST IDENTIFICATION HAS CHANGED|Load key .*:|identity file .* not accessible' "$rq1_error_log" ||
                ! LC_ALL=C grep -Eiq 'Connection (timed out|refused|reset|closed)|Operation timed out|No route to host|Network is unreachable' "$rq1_error_log"; then
            echo 'SSH authentication, host verification or another non-transient error requires review.' >&2
            return "$rq1_probe_exit"
        fi
        if ((rq1_probe < 12)); then
            echo 'SSH is not ready; checking again in 5 seconds.'
            sleep 5
        fi
    done
    echo 'SSH readiness timed out. Check the VM state and current console IP; no experiment was launched.' >&2
    return 255
}
