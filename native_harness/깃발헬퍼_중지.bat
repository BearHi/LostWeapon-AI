@echo off
cd /d "%~dp0"
if not exist checkpoints mkdir checkpoints
type nul > checkpoints\route_rule_helper.stop
echo Stop requested. The trainer will save after its current decision.
pause
