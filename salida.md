cesar@DESKTOP-VJO5HF3:~/tokenxllm/scripts/sepolia$ ./01_compile.sh 
==> Compilando contratos con scarb --release build
   Compiling tokenxllm v0.1.0 (/home/cesar/tokenxllm/Scarb.toml)
    Finished `release` profile target(s) in 1 second
==> Contratos disponibles:
==> Contratos disponibles:
UsageManager
tokenxllm
cesar@DESKTOP-VJO5HF3:~/tokenxllm/scripts/sepolia$ ./02_declare_aic.sh 
==> Declarando contrato tokenxllm
   Compiling tokenxllm v0.1.0 (/home/cesar/tokenxllm/Scarb.toml)
    Finished `release` profile target(s) in 1 second
Success: Declaration completed

Class Hash:       0x317ab82ed36ab500d211718f911b14085ecb0b768cbfc9681ec8e285b0e2203
Transaction Hash: 0x7527c8b0c8b6765d11d083f38dc0287c23d7e34990a47ec37b6853cb0ce7b05

To see declaration details, visit:
class: https://sepolia.starkscan.co/class/0x0317ab82ed36ab500d211718f911b14085ecb0b768cbfc9681ec8e285b0e2203
transaction: https://sepolia.starkscan.co/tx/0x07527c8b0c8b6765d11d083f38dc0287c23d7e34990a47ec37b6853cb0ce7b05
CLASS_HASH_AIC=0x317ab82ed36ab500d211718f911b14085ecb0b768cbfc9681ec8e285b0e2203

cesar@DESKTOP-VJO5HF3:~/tokenxllm/scripts/sepolia$ ./03_deploy_aic.sh 
==> Desplegando contrato AIC
Success: Deployment completed

Contract Address: 0x0083ce9c62abf9c717fb824f346746d25b8181c254acd7ed9fef7842ef0179f5
Transaction Hash: 0x05902d467601508100b3b7e2725a103ec9a9f9103009b9a2b5e987ff59e137a3

To see deployment details, visit:
contract: https://sepolia.starkscan.co/contract/0x0083ce9c62abf9c717fb824f346746d25b8181c254acd7ed9fef7842ef0179f5
transaction: https://sepolia.starkscan.co/tx/0x05902d467601508100b3b7e2725a103ec9a9f9103009b9a2b5e987ff59e137a3
AIC_ADDR=0x0083ce9c62abf9c717fb824f346746d25b8181c254acd7ed9fef7842ef0179f5

cesar@DESKTOP-VJO5HF3:~/tokenxllm/scripts/sepolia$ ./05_deploy_usage_manager.sh 
==> Desplegando contrato UsageManager
Success: Deployment completed

Contract Address: 0x044af39b19758d164f398c76941df5577a3c85e733db61e12e04803122ce28b8
Transaction Hash: 0x0364f3d5c33f9cf4771d4d61bc4dfdeacc73f346ade0edca48e3f35737279778

To see deployment details, visit:
contract: https://sepolia.starkscan.co/contract/0x044af39b19758d164f398c76941df5577a3c85e733db61e12e04803122ce28b8
transaction: https://sepolia.starkscan.co/tx/0x0364f3d5c33f9cf4771d4d61bc4dfdeacc73f346ade0edca48e3f35737279778
UM_ADDR=0x044af39b19758d164f398c76941df5577a3c85e733db61e12e04803122ce28b8
cesar@DESKTOP-VJO5HF3:~/tokenxllm/scripts/sepolia$ 