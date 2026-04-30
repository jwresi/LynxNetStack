package netbox

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"path"
	"strings"
	"time"

	"lynxdhcp/internal/data"
)

type Client struct {
	baseURL    string
	token      string
	httpClient *http.Client
}

type DeviceListResponse struct {
	Results []Device `json:"results"`
}

type TenantListResponse struct {
	Results []Tenant `json:"results"`
}

type Tenant struct {
	ID          int    `json:"id"`
	Name        string `json:"name"`
	Slug        string `json:"slug"`
	Description string `json:"description"`
	Comments    string `json:"comments"`
}

type Device struct {
	ID       int        `json:"id"`
	Name     string     `json:"name"`
	Serial   string     `json:"serial"`
	AssetTag string     `json:"asset_tag"`
	Status   NamedValue `json:"status"`
	Role     NamedValue `json:"role"`
	Device   DeviceType `json:"device_type"`
	Site     NamedValue `json:"site"`
	Primary4 *IPWrapper `json:"primary_ip4"`
}

type DeviceType struct {
	Model string `json:"model"`
}

type IPWrapper struct {
	Address string `json:"address"`
}

type NamedValue struct {
	Label string `json:"label"`
	Name  string `json:"name"`
	Value string `json:"value"`
}

func New(baseURL, token string) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		token:   token,
		httpClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

func (c *Client) Enabled() bool {
	return c.baseURL != "" && c.token != ""
}

func (c *Client) ListHardware(ctx context.Context) ([]data.HardwareAsset, error) {
	if !c.Enabled() {
		return nil, fmt.Errorf("netbox not configured")
	}

	u, err := url.Parse(c.baseURL)
	if err != nil {
		return nil, err
	}
	u.Path = path.Join(u.Path, "/api/dcim/devices/")
	q := u.Query()
	q.Set("limit", "100")
	u.RawQuery = q.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Token "+c.token)
	req.Header.Set("Accept", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("netbox returned status %d", resp.StatusCode)
	}

	var payload DeviceListResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil, err
	}

	assets := make([]data.HardwareAsset, 0, len(payload.Results))
	for _, device := range payload.Results {
		managementIP := ""
		if device.Primary4 != nil {
			managementIP = device.Primary4.Address
		}
		assets = append(assets, data.HardwareAsset{
			ID:           fmt.Sprintf("nbx-%d", device.ID),
			Source:       "netbox",
			NetBoxID:     device.ID,
			Name:         valueOr(device.Name, fmt.Sprintf("device-%d", device.ID)),
			Role:         preferredName(device.Role),
			Model:        device.Device.Model,
			Serial:       device.Serial,
			AssetTag:     device.AssetTag,
			Site:         preferredName(device.Site),
			Status:       strings.ToLower(valueOr(preferredName(device.Status), "active")),
			ManagementIP: managementIP,
		})
	}

	return assets, nil
}

func (c *Client) ListCustomers(ctx context.Context) ([]data.Customer, error) {
	if !c.Enabled() {
		return nil, fmt.Errorf("netbox not configured")
	}

	u, err := url.Parse(c.baseURL)
	if err != nil {
		return nil, err
	}
	u.Path = path.Join(u.Path, "/api/tenancy/tenants/")
	q := u.Query()
	q.Set("limit", "100")
	u.RawQuery = q.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Token "+c.token)
	req.Header.Set("Accept", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("netbox returned status %d", resp.StatusCode)
	}

	var payload TenantListResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil, err
	}

	customers := make([]data.Customer, 0, len(payload.Results))
	for _, tenant := range payload.Results {
		customers = append(customers, data.Customer{
			ID:          tenant.ID,
			Name:        tenant.Name,
			Slug:        tenant.Slug,
			Description: tenant.Description,
			Comments:    tenant.Comments,
		})
	}
	return customers, nil
}

func preferredName(value NamedValue) string {
	return valueOr(value.Label, valueOr(value.Name, value.Value))
}

func valueOr(value, fallback string) string {
	if strings.TrimSpace(value) != "" {
		return value
	}
	return fallback
}
