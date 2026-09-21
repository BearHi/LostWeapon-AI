@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "checkpoints" mkdir "checkpoints"
echo Starting local LostWeapon training. Press Ctrl+C to stop.
python "train_local_dqn.py" "private_snapshots\hun1_full.zip" "..\훈련용맵\훈1.LMF" --episodes 200 --max-steps 1500 --action-repeat 2 --checkpoint "checkpoints\hun1_dqn.pt" --resume
pause
