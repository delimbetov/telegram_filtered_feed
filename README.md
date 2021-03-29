Project is frozen, but if any one feels like picking it up I will be happy to help.

# Overview
Telegram bot that allows you to combine multiple public channels you are interested in into a single channel - your personal feed. 
# Motivation
It simplifies content consuming, lets you clean up your chats out of public channels.
# Internals
Project consists of 3 components:
1. The Bot itself, which is responsible for user interaction: handling command and forwarding messages to user channels.
2. The Forwarder service, which is responsible for joining channels followed by users and forwarding messages to the bot.
3. The Resolver service, which is responsible for resolving links to private channels.
# How To Deploy
I was running it on the DigitalOcean droplet. Check out deploy_centos8_1.sh file for detailed instructions - it's mostly correct, but it has to be done manually, don't expect it to work as a script :)
