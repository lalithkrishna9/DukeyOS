package docker_test

import (
	"fmt"
	"testing"

	"dukeyos.local/appmanagement/pkg/docker"
)

func TestGetDir(t *testing.T) {
	fmt.Println(docker.GetDir("", "config"))
}
