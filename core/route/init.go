/*
 * @Author: LinkLeong link@icewhale.org
 * @Date: 2022-11-15 15:51:44
 * @LastEditors: LinkLeong
 * @LastEditTime: 2022-11-15 15:55:16
 * @FilePath: /DukeyOS/route/init.go
 * @Description:
 * @Website: https://www.casaos.io
 * Copyright (c) 2022 by icewhale, All Rights Reserved.
 */
package route

import (
	"fmt"
	"os"
	"strings"
	"time"

	"dukeyos.local/common/utils/logger"
	"dukeyos.local/core/pkg/samba"
	"dukeyos.local/core/pkg/utils/file"
	"dukeyos.local/core/service"
	"go.uber.org/zap"
)

func InitFunction() {
	go InitNetworkMount()
}

func InitNetworkMount() {
	time.Sleep(time.Second * 10)
	connections := service.MyService.Connections().GetConnectionsList()
	for _, v := range connections {
		connection := service.MyService.Connections().GetConnectionByID(fmt.Sprint(v.ID))
		directories, err := samba.GetSambaSharesList(connection.Host, connection.Port, connection.Username, connection.Password)
		if err != nil {
			service.MyService.Connections().DeleteConnection(fmt.Sprint(connection.ID))
			logger.Error("mount samba err", zap.Any("err", err), zap.Any("info", connection))
			continue
		}
		baseHostPath := "/mnt/" + connection.Host

		mountPointList, err := service.MyService.System().GetDirPath(baseHostPath)
		if err != nil {
			logger.Error("get mount point err", zap.Any("err", err))
			continue
		}
		for _, v := range mountPointList {
			service.MyService.Connections().UnmountSmaba(v.Path)
		}

		os.RemoveAll(baseHostPath)

		file.IsNotExistMkDir(baseHostPath)
		for _, v := range directories {
			mountPoint := baseHostPath + "/" + v
			file.IsNotExistMkDir(mountPoint)
			service.MyService.Connections().MountSmaba(connection.Username, connection.Host, v, connection.Port, mountPoint, connection.Password)
		}
		connection.Directories = strings.Join(directories, ",")
		service.MyService.Connections().UpdateConnection(&connection)
	}
	err := service.MyService.Storage().CheckAndMountAll()
	if err != nil {
		logger.Error("mount storage err", zap.Any("err", err))
	}
}
