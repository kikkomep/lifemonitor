#!/bin/bash

url="https://seek:3000/oauth/authorize"
timeout_seconds=${1:-30}
DEBUG=${DEBUG:-0}
SEEK_FINAL_WAIT_TIME=${SEEK_FINAL_WAIT_TIME:-0}

# Log the environment variables
if [ "$DEBUG" == "1" ]; then
    echo -e "\nDEBUG: URL: $url"
    echo -e "DEBUG: Timeout seconds: $timeout_seconds"
    echo -e "DEBUG: SEEK_FINAL_WAIT_TIME: $SEEK_FINAL_WAIT_TIME"
fi

# Function to check if the server is available
check_server() {
    response=$(curl -Is "$url" --insecure | head -n 1)
    status_code=$(echo "$response" | awk '{print $2}')
    
    if [ "$status_code" == "302" ]; then
        if [[ $SEEK_FINAL_WAIT_TIME -gt 0 ]]; then
            if [ "$DEBUG" == "1" ]; then
                echo -e "\nDEBUG: Seek is available, but waiting for $SEEK_FINAL_WAIT_TIME seconds..."
            fi
            sleep $SEEK_FINAL_WAIT_TIME
        fi
        echo -en "\e[1mOK\e[0m: Seek is now available!\n"
        exit 0
    fi
}

# Wait until the server is available or timeout is reached
elapsed_seconds=0
echo -en "\n\e[1mWaiting for Seek to be available... \e[0m"
while [ $elapsed_seconds -lt $timeout_seconds ]; do
    check_server
    sleep 5
    if [ "$DEBUG" == "1" ]; then
        echo -e "\nDEBUG: Elapsed time: $elapsed_seconds seconds ($timeout_seconds seconds timeout) ... "
    fi
    elapsed_seconds=$((elapsed_seconds + 1))
done
if [ "$DEBUG" == "1" ]; then
    echo -e "DEBUG: Timeout reached: elapsed time $elapsed_seconds seconds"
fi
echo -en "\e[1mERROR\e[0m: Seek is not available.\n"
exit 1
