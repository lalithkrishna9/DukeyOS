# DukeyOS-MessageBus

[![Go Reference](https://pkg.go.dev/badge/dukeyos.local/messagebus.svg)](https://pkg.go.dev/dukeyos.local/messagebus) [![Go Report Card](https://goreportcard.com/badge/dukeyos.local/messagebus)](https://goreportcard.com/report/dukeyos.local/messagebus) [![goreleaser](https://dukeyos.local/messagebus/actions/workflows/release.yml/badge.svg)](https://dukeyos.local/messagebus/actions/workflows/release.yml) [![codecov](https://codecov.io/gh/IceWhaleTech/DukeyOS-MessageBus/branch/main/graph/badge.svg?token=U4S4ZSZAL9)](https://codecov.io/gh/IceWhaleTech/DukeyOS-MessageBus)

Message bus accepts events and actions from various sources and delivers them to subscribers.

See [openapi.yaml](./api/message_bus/openapi.yaml) for API specification.




## publish api to npm

### edit version in package.json

### run
```bash
yarn

yarn start
```

### publish

Manual publish
```bash
yarn publish
```

Auto publish
```bash 
git push origin dev**
```