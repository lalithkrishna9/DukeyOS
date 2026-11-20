package common

import (
	"dukeyos.local/core/codegen/message_bus"
)

// devtype -> action -> event
var EventTypes = []message_bus.EventType{
	{Name: "dukeyos:system:utilization", SourceID: SERVICENAME, PropertyTypeList: []message_bus.PropertyType{}},
	{Name: "dukeyos:file:recover", SourceID: SERVICENAME, PropertyTypeList: []message_bus.PropertyType{}},
	{Name: "dukeyos:file:operate", SourceID: SERVICENAME, PropertyTypeList: []message_bus.PropertyType{}},
}
