// Digithings DigiChat ACA + ACR + CAE (Phase 3).
// Prefer applying via the live az CLI bootstrap already run; this module
// documents the desired state for re-create / disaster recovery.

@description('Azure region')
param location string = 'eastus2'

@description('Digichat image (ACR)')
param digichatImage string = 'digithingschatregistry.azurecr.io/digichat:phase3-preview'

output interimFqdn string = 'digichat.agreeablepebble-8440dc16.eastus2.azurecontainerapps.io'
output publicHostname string = 'chat.digithings.ai'
output image string = digichatImage
output locationOut string = location
