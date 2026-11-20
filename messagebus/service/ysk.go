package service

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"dukeyos.local/common/utils/logger"
	"dukeyos.local/messagebus/common"
	"dukeyos.local/messagebus/model"
	"dukeyos.local/messagebus/pkg/ysk"
	"dukeyos.local/messagebus/repository"
	"dukeyos.local/messagebus/utils"
	"go.uber.org/zap"
)

type YSKService struct {
	repository       *repository.Repository
	ws               *EventServiceWS
	eventTypeService *EventTypeService
}

const YSKOnboardingFinishedKey = "ysk_onboarding_finished"

func NewYSKService(
	repository *repository.Repository,
	ws *EventServiceWS,
	ets *EventTypeService,
) *YSKService {
	return &YSKService{
		repository:       repository,
		ws:               ws,
		eventTypeService: ets,
	}
}

func (s *YSKService) YskCardList(ctx context.Context) ([]ysk.YSKCard, error) {
	cardList, err := (*s.repository).GetYSKCardList()
	if err != nil {
		return []ysk.YSKCard{}, err
	}
	return cardList, nil
}

func (s *YSKService) UpsertYSKCard(ctx context.Context, yskCard ysk.YSKCard) error {
	// don't store short notice cards
	if yskCard.CardType == ysk.CardTypeShortNote {
		return nil
	}
	err := (*s.repository).UpsertYSKCard(yskCard)
	return err
}

func (s *YSKService) DeleteYSKCard(ctx context.Context, id string) error {
	return (*s.repository).DeleteYSKCard(id)
}

func (s *YSKService) Start(init bool) {
	// 判断数据库
	if init {
		// only run once
		settings, err := (*s.repository).GetSettings(YSKOnboardingFinishedKey)

		if settings == nil && err.Error() == "record not found" {
			s.UpsertYSKCard(context.Background(), utils.DukeyOSDataStationNotice)
			s.UpsertYSKCard(context.Background(), utils.DukeyOSFileManagementNotice)
			s.UpsertYSKCard(context.Background(), utils.DukeyOSRemoteAccessNotice)
			(*s.repository).UpsertSettings(model.Settings{
				Key:   YSKOnboardingFinishedKey,
				Value: "true",
			})
		}
	}
	// register event
	s.eventTypeService.RegisterEventType(model.EventType{
		SourceID: common.SERVICENAME,
		Name:     common.EventTypeYSKCardUpsert.Name,
	})

	s.eventTypeService.RegisterEventType(model.EventType{
		SourceID: common.SERVICENAME,
		Name:     common.EventTypeYSKCardDelete.Name,
	})

	// the event is frontend event.
	// in dukeyos, it register by frontend. register by who call it.
	// but in dukeyos ui gen 2. the frontend lose register event type.
	// so we had to register it here.
	// but i think is not a good idea. it should register by who call it.
	s.eventTypeService.RegisterEventType(model.EventType{
		SourceID: "dukeyos-ui",
		Name:     "dukeyos-ui:app:mircoapp_communicate",
	})

	channel, err := s.ws.Subscribe(common.SERVICENAME, []string{
		common.EventTypeYSKCardUpsert.Name, common.EventTypeYSKCardDelete.Name,
	})
	if err != nil {
		logger.Error("failed to subscribe to event", zap.Error(err))
		return
	}

	go func() {
		for {
			select {
			case event, ok := <-channel:
				if !ok {
					log.Println("channel closed")
				}
				switch event.Name {
				case common.EventTypeYSKCardUpsert.Name:
					var card ysk.YSKCard
					err := json.Unmarshal([]byte(event.Properties[common.PropertyTypeCardBody.Name]), &card)
					if err != nil {
						logger.Error("failed to umarshal ysk card", zap.Error(err))
						continue
					}
					err = s.UpsertYSKCard(context.Background(), card)
					if err != nil {
						logger.Error("failed to upsert ysk card", zap.Error(err))
					}
				case common.EventTypeYSKCardDelete.Name:
					err = s.DeleteYSKCard(context.Background(), event.Properties[common.PropertyTypeCardID.Name])
					if err != nil {
						logger.Error("failed to delete ysk card", zap.Error(err))
					}
				default:
					fmt.Println(event)
				}
			}
		}
	}()
}
