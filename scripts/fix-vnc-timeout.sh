#!/bin/bash
# Run with: sudo bash fix-vnc-timeout.sh
sudo defaults write /Library/Preferences/com.apple.RemoteManagement VNCIdleTimeout -int 0
sudo defaults write /Library/Preferences/com.apple.RemoteManagement VNCInactiveTimeout -int 0
sudo defaults write /Library/Preferences/com.apple.RemoteManagement ScreenSharingReqPermEnabled -bool false
sudo defaults write /Library/Preferences/com.apple.RemoteManagement LoadRemoteManagementMenuExtra -bool false
sudo defaults write /Library/Preferences/com.apple.RemoteDesktop DoNotSendSystemKeys -bool false
sudo /System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart -restart -agent -console
echo "Done. VNC timeouts disabled."
