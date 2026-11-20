package v2

import codegen "dukeyos.local/usersvc/codegen/user_service"

type UserService struct{}

func NewUserService() codegen.ServerInterface {
	return &UserService{}
}
