@echo off
set immich_path=%1
set upload_path=%2
set server_url=%3
set api_key=%4

%immich_path% -server %server_url% -key %api_key% upload %upload_path%
pause