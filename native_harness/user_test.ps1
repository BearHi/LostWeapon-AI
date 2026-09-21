param(
  [Parameter(Mandatory=$true)][ValidateSet('hun2','hun5','hun6','hun7','hun12')][string]$Fixture,
  [string]$Schedule = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$snapshots = @{
  hun2 = 'private_snapshots/hun2_live.zip'
  hun5 = 'private_snapshots/hun5_live.zip'
  hun6 = 'private_snapshots/hun6_live.zip'
  hun7 = 'private_snapshots/hun7_live.zip'
  hun12 = 'private_snapshots/hun12_live.zip'
}
$maps = @{
  hun2 = '../훈련용맵/훈2.LMF'
  hun5 = '../훈련용맵/훈5.LMF'
  hun6 = '../훈련용맵/훈6.LMF'
  hun7 = '../훈련용맵/훈7.LMF'
  hun12 = '../훈련용맵/훈12.LMF'
}
$defaultSchedules = @{
  hun2 = '[{"keys":["RIGHT"],"ticks":32},{"keys":["RIGHT","UP"],"ticks":20}]'
  hun5 = '[{"keys":["RIGHT"],"ticks":45},{"keys":["RIGHT","C"],"ticks":30}]'
  hun6 = '[{"keys":["RIGHT","UP"],"ticks":40}]'
  hun7 = '[{"keys":["RIGHT"],"ticks":64},{"keys":["UP"],"ticks":30}]'
  hun12 = '[{"keys":[],"ticks":30}]'
}
if ([string]::IsNullOrWhiteSpace($Schedule)) { $Schedule = $defaultSchedules[$Fixture] }
Push-Location $root
try {
  python run_training_episode.py $snapshots[$Fixture] $maps[$Fixture] $Schedule "evidence/user_test_$Fixture.json"
} finally { Pop-Location }
