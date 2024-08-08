#!/bin/bash

# Check if virtual environment exists
if [ ! -d "lurkbotEnv" ]; then
    echo "Virtual environment not found. Please run setup_lurkbot.sh first."
    exit
fi

# Activate the virtual environment
source lurkbotEnv/Scripts/activate

# Run the bot
python lurkbot.py

# Deactivate the virtual environment after the bot stops
deactivate
