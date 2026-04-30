package config

import (
	"encoding/json"
	"os"
	"path/filepath"

	"github.com/joho/godotenv"
)

func LoadKnownEnvFiles() {
	paths := []string{
		".env",
		"<legacy old-jake>/.env",
		"<legacy sibling repo>/.env",
	}

	for _, path := range paths {
		if _, err := os.Stat(path); err == nil {
			_ = godotenv.Overload(path)
		}
	}

	loadAnythingLLMNetBoxEnv()
}

func loadAnythingLLMNetBoxEnv() {
	if os.Getenv("NETBOX_BASE_URL") != "" && os.Getenv("NETBOX_TOKEN") != "" {
		return
	}

	mcpPath := os.Getenv("ANYTHINGLLM_MCP_SERVERS_JSON")
	if mcpPath == "" {
		mcpPath = filepath.Join(
			os.Getenv("HOME"),
			"Library",
			"Application Support",
			"anythingllm-desktop",
			"storage",
			"plugins",
			"anythingllm_mcp_servers.json",
		)
	}

	raw, err := os.ReadFile(mcpPath)
	if err != nil {
		return
	}

	var payload struct {
		MCPServers map[string]struct {
			Env map[string]string `json:"env"`
		} `json:"mcpServers"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		return
	}

	entry, ok := payload.MCPServers["netbox_mcp"]
	if !ok {
		return
	}

	if os.Getenv("NETBOX_BASE_URL") == "" {
		if value := entry.Env["NETBOX_BASE_URL"]; value != "" {
			_ = os.Setenv("NETBOX_BASE_URL", value)
		} else if value := entry.Env["NETBOX_URL"]; value != "" {
			_ = os.Setenv("NETBOX_BASE_URL", value)
		}
	}
	if os.Getenv("NETBOX_TOKEN") == "" {
		if value := entry.Env["NETBOX_TOKEN"]; value != "" {
			_ = os.Setenv("NETBOX_TOKEN", value)
		}
	}
}
