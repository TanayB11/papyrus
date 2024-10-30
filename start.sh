#!/bin/bash
cd server
mkdir -p data
python3 -m venv env && source env/bin/activate
pip3 install -r requirements.txt
make prod &
pid1=$!

cd ..

yarn install
yarn dev --host &
pid2=$!

# Function to kill both processes
cleanup() {
    echo "Terminating processes..."
    kill $pid1 $pid2
    wait $pid1 $pid2 2>/dev/null
    echo "Processes terminated."
}

# Trap Ctrl-C (SIGINT) and call the cleanup function
trap cleanup SIGINT

# Wait for both processes to finish
wait $pid1 $pid2
