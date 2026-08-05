// DigiThings DigiChat — placeholder only.
// Do NOT deploy into DataTap subscriptions (e.g. DataTap WebSite
// fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0). Hosting direction is website-path
// first; pause chat.digithings.ai ACA until DigiThings-owned infra is chosen.

@description('Azure region — DigiThings subscription only')
param location string = 'eastus2'

output note string = 'Do not deploy DigiThings digichat into DataTap Azure. See infra/digichat-digithings/README.md'
output locationOut string = location
