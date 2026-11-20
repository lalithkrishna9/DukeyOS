package service

import (
	"dukeyos.local/appmanagement/codegen"
	"dukeyos.local/appmanagement/common"
	"dukeyos.local/common/utils/logger"
	"github.com/compose-spec/compose-go/loader"
	"github.com/compose-spec/compose-go/types"
)

type App types.ServiceConfig

func (a *App) StoreInfo() (codegen.AppStoreInfo, error) {
	var storeInfo codegen.AppStoreInfo

	ex, ok := a.Extensions[common.ComposeExtensionNameXDukeyOS]
	if !ok {
		logger.Error("extension `x-casaos` not found")
		// return storeInfo, ErrComposeExtensionNameXDukeyOSNotFound
	}

	// add image to store info for check stable version function.
	storeInfo.Image = a.Image

	if err := loader.Transform(ex, &storeInfo); err != nil {
		return storeInfo, err
	}

	return storeInfo, nil
}
