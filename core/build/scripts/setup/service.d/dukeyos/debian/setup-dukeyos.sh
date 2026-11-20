#!/bin/bash
###
# @Author: LinkLeong link@icewhale.org
# @Date: 2022-08-25 11:41:22
 # @LastEditors: LinkLeong
 # @LastEditTime: 2022-08-31 17:54:17
 # @FilePath: /DukeyOS/build/scripts/setup/service.d/dukeyos/debian/setup-dukeyos.sh
# @Description:

# @Website: https://www.casaos.io
# Copyright (c) 2022 by icewhale, All Rights Reserved.
###

set -e

APP_NAME="dukeyos"

# copy config files
CONF_PATH=/etc/dukeyos
OLD_CONF_PATH=/etc/dukeyos.conf
CONF_FILE=${CONF_PATH}/${APP_NAME}.conf
CONF_FILE_SAMPLE=${CONF_PATH}/${APP_NAME}.conf.sample


if [ -f "${OLD_CONF_PATH}" ]; then
    echo "copy old conf"
    cp "${OLD_CONF_PATH}" "${CONF_FILE}"
fi
if [ ! -f "${CONF_FILE}" ]; then
    echo "Initializing config file..."
    cp -v "${CONF_FILE_SAMPLE}" "${CONF_FILE}"
fi


systemctl daemon-reload

# enable service (without starting)
echo "Enabling service..."
systemctl enable --force --no-ask-password "dukeyos-core.service"
