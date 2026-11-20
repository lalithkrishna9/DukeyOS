package config

import (
	"path/filepath"

	"dukeyos.local/common/utils/constants"
)

var (
	AppManagementConfigFilePath    = filepath.Join(constants.DefaultConfigPath, "app-management.conf")
	AppManagementGlobalEnvFilePath = filepath.Join(constants.DefaultConfigPath, "env")
	RemoveRuntimeIfNoNvidiaGPUFlag = false
)
