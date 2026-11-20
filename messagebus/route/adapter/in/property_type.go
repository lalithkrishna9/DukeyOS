package in

import (
	"dukeyos.local/messagebus/codegen"
	"dukeyos.local/messagebus/model"
)

func PropertyTypeAdapter(propertyType codegen.PropertyType) model.PropertyType {
	return model.PropertyType{
		Name: propertyType.Name,
	}
}
