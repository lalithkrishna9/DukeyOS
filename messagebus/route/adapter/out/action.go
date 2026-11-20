package out

import (
	"time"

	"dukeyos.local/common/utils"
	"dukeyos.local/messagebus/codegen"
	"dukeyos.local/messagebus/model"
)

func ActionAdapter(action model.Action) codegen.Action {
	return codegen.Action{
		SourceID:   action.SourceID,
		Name:       action.Name,
		Properties: action.Properties,
		Timestamp:  utils.Ptr(time.Unix(action.Timestamp, 0)),
	}
}
