package pkg

import (
	"dukeyos.local/appmanagement/codegen"
	"dukeyos.local/appmanagement/common"
	"dukeyos.local/appmanagement/service"
	"github.com/compose-spec/compose-go/loader"
)

func VaildDockerCompose(yaml []byte) (err error) {
	err = nil
	// recover
	defer func() {
		if r := recover(); r != nil {
			err = r.(error)
		}
	}()
	docker, err := service.NewComposeAppFromYAML(yaml, false, false)

	ex, ok := docker.Extensions[common.ComposeExtensionNameXDukeyOS]
	if !ok {
		return service.ErrComposeExtensionNameXDukeyOSNotFound
	}

	var storeInfo codegen.ComposeAppStoreInfo
	if err = loader.Transform(ex, &storeInfo); err != nil {
		return
	}

	return
}
