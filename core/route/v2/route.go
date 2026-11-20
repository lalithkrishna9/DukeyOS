package v2

import (
	"dukeyos.local/core/codegen"
	"dukeyos.local/core/service"
)

type DukeyOS struct {
	fileUploadService *service.FileUploadService
}

func NewDukeyOS() codegen.ServerInterface {
	return &DukeyOS{
		fileUploadService: service.NewFileUploadService(),
	}
}
