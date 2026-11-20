package common

import (
	"log"
	"os"
	"path/filepath"

	"github.com/spf13/viper"

	"dukeyos.local/common/utils/constants"
)

const (
	ConfigKeyLogPath     = "gateway.LogPath"
	ConfigKeyLogSaveName = "gateway.LogSaveName"
	ConfigKeyLogFileExt  = "gateway.LogFileExt"
	ConfigKeyGatewayPort = "gateway.Port"
	ConfigKeyGatewayBind = "gateway.Bind"
	ConfigKeyRuntimePath = "common.RuntimePath"

	GatewayName       = "gateway"
	GatewayConfigType = "ini"
)

func LoadConfig() (*viper.Viper, error) {
	config := viper.New()

	config.SetDefault(ConfigKeyLogPath, constants.DefaultLogPath)
	config.SetDefault(ConfigKeyLogSaveName, GatewayName)
	config.SetDefault(ConfigKeyLogFileExt, "log")

	config.SetDefault(ConfigKeyGatewayBind, "127.0.0.1")
	config.SetDefault(ConfigKeyRuntimePath, constants.DefaultRuntimePath) // See https://refspecs.linuxfoundation.org/FHS_3.0/fhs/ch05s13.html

	config.SetConfigName(GatewayName)
	config.SetConfigType(GatewayConfigType)

	if currentDirectory, err := os.Getwd(); err != nil {
		log.Println(err)
	} else {
		config.AddConfigPath(currentDirectory)
		config.AddConfigPath(filepath.Join(currentDirectory, "conf"))
	}

	if configPath, success := os.LookupEnv("DUKEYOS_CONFIG_PATH"); success {
		config.AddConfigPath(configPath)
	}

	config.AddConfigPath(constants.DefaultConfigPath)

	if err := config.ReadInConfig(); err != nil {
		return nil, err
	}

	return config, nil
}
