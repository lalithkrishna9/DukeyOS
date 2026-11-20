package out

import (
	"dukeyos.local/messagebus/codegen"
	"dukeyos.local/messagebus/model"
)

func PropertyTypeAdapter(propertyType model.PropertyType) codegen.PropertyType {
	return codegen.PropertyType{
		Name: propertyType.Name,
	}
}
