package data

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"sync"
	"time"
)

type Store struct {
	mu   sync.RWMutex
	path string
	data State
}

type State struct {
	Summary                DashboardSummary        `json:"summary"`
	Subscribers            []Subscriber            `json:"subscribers"`
	Network                NetworkView             `json:"network"`
	Hardware               []HardwareAsset         `json:"hardware"`
	Checkouts              []CheckoutRecord        `json:"checkouts"`
	HardwareCheckoutDrafts []HardwareCheckoutDraft `json:"hardwareCheckoutDrafts"`
	SiteOverlays           []SiteOverlay           `json:"siteOverlays"`
	SiteDrafts             []SiteDraft             `json:"siteDrafts"`
	Findings               []Finding               `json:"findings"`
	Changes                []ChangePlan            `json:"changes"`
	Billing                BillingOverview         `json:"billing"`
	Config                 PlatformConfig          `json:"config"`
	Events                 []ActivityEvent         `json:"events"`
}

type CreateSubscriberInput struct {
	Name           string  `json:"name"`
	Site           string  `json:"site"`
	Plan           string  `json:"plan"`
	CircuitID      string  `json:"circuitId"`
	RemoteID       string  `json:"remoteId"`
	Relay          string  `json:"relay"`
	VLAN           int     `json:"vlan"`
	IPv4           string  `json:"ipv4"`
	CPEMAC         string  `json:"cpeMac"`
	MonthlyRevenue float64 `json:"monthlyRevenue"`
}

func NewStore(path string) (*Store, error) {
	store := &Store{path: path}
	if err := store.loadOrSeed(); err != nil {
		return nil, err
	}
	return store, nil
}

func (s *Store) Summary() DashboardSummary {
	s.mu.RLock()
	defer s.mu.RUnlock()
	summary := s.data.Summary
	summary.SubscribersTotal = len(s.data.Subscribers)
	summary.ActiveRelays = len(s.data.Network.Relays)
	summary.OpenFindings = 0
	summary.OnlineSubscribers = 0
	for _, sub := range s.data.Subscribers {
		if sub.Status == "online" || sub.Status == "degraded" {
			summary.OnlineSubscribers++
		}
	}
	for _, finding := range s.data.Findings {
		if finding.Status == "" || finding.Status == "open" {
			summary.OpenFindings++
		}
	}
	return summary
}

func (s *Store) Subscribers() []Subscriber {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return slices.Clone(s.data.Subscribers)
}

func (s *Store) Network() NetworkView {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.data.Network
}

func (s *Store) Hardware() HardwareInventory {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return HardwareInventory{
		Assets:    slices.Clone(s.data.Hardware),
		Checkouts: slices.Clone(s.data.Checkouts),
	}
}

func (s *Store) Findings() []Finding {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return slices.Clone(s.data.Findings)
}

func (s *Store) Changes() []ChangePlan {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return slices.Clone(s.data.Changes)
}

func (s *Store) Billing() BillingOverview {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.data.Billing
}

func (s *Store) Config() PlatformConfig {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.data.Config
}

func (s *Store) Events() []ActivityEvent {
	s.mu.RLock()
	defer s.mu.RUnlock()
	events := make([]ActivityEvent, 0, len(s.data.Events))
	for _, event := range s.data.Events {
		switch event.Category {
		case "hardware", "draft", "approval", "source":
			events = append(events, event)
		}
	}
	return events
}

func (s *Store) SiteOverlays() []SiteOverlay {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return slices.Clone(s.data.SiteOverlays)
}

func (s *Store) SiteDrafts() []SiteDraft {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return slices.Clone(s.data.SiteDrafts)
}

func (s *Store) HardwareCheckoutDrafts() []HardwareCheckoutDraft {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return slices.Clone(s.data.HardwareCheckoutDrafts)
}

func (s *Store) CreateSubscriber(input CreateSubscriberInput) (Subscriber, error) {
	if strings.TrimSpace(input.Name) == "" || strings.TrimSpace(input.CircuitID) == "" {
		return Subscriber{}, errors.New("name and circuitId are required")
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	now := time.Now()
	id := fmt.Sprintf("sub-%d", now.Unix())
	subscriber := Subscriber{
		ID:             id,
		Name:           strings.TrimSpace(input.Name),
		Site:           strings.TrimSpace(input.Site),
		Status:         "pending",
		Plan:           strings.TrimSpace(input.Plan),
		CircuitID:      strings.TrimSpace(input.CircuitID),
		RemoteID:       strings.TrimSpace(input.RemoteID),
		Relay:          strings.TrimSpace(input.Relay),
		VLAN:           input.VLAN,
		IPv4:           strings.TrimSpace(input.IPv4),
		CPEMAC:         strings.TrimSpace(strings.ToUpper(input.CPEMAC)),
		LastSeen:       "awaiting first discover",
		SignalLabel:    "not yet provisioned",
		MonthlyRevenue: input.MonthlyRevenue,
	}

	s.data.Subscribers = append([]Subscriber{subscriber}, s.data.Subscribers...)
	s.pushEvent(ActivityEvent{
		When:     now.Format(time.RFC3339),
		Category: "subscriber",
		Message:  fmt.Sprintf("Queued subscriber %s on %s using relay %s.", subscriber.Name, subscriber.CircuitID, subscriber.Relay),
	})

	return subscriber, s.persistLocked()
}

func (s *Store) AckFinding(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	for idx := range s.data.Findings {
		if s.data.Findings[idx].ID != id {
			continue
		}
		if s.data.Findings[idx].Status == "acked" {
			return nil
		}

		s.data.Findings[idx].Status = "acked"
		s.data.Findings[idx].AckedAt = time.Now().Format(time.RFC3339)
		s.pushEvent(ActivityEvent{
			When:     time.Now().Format(time.RFC3339),
			Category: "finding",
			Message:  fmt.Sprintf("Acknowledged finding %s on %s.", s.data.Findings[idx].Title, s.data.Findings[idx].Device),
		})
		return s.persistLocked()
	}

	return errors.New("finding not found")
}

func (s *Store) ApproveChange(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	for idx := range s.data.Changes {
		if s.data.Changes[idx].ID != id {
			continue
		}
		s.data.Changes[idx].Status = "approved"
		s.data.Changes[idx].ApprovedAt = time.Now().Format(time.RFC3339)
		s.pushEvent(ActivityEvent{
			When:     time.Now().Format(time.RFC3339),
			Category: "change",
			Message:  fmt.Sprintf("Approved change %s.", s.data.Changes[idx].Scope),
		})
		return s.persistLocked()
	}

	return errors.New("change not found")
}

func (s *Store) ReplaceHardware(assets []HardwareAsset, source string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	checkoutByAsset := map[string]CheckoutRecord{}
	for _, checkout := range s.data.Checkouts {
		checkoutByAsset[checkout.AssetID] = checkout
	}

	for idx := range assets {
		if checkout, ok := checkoutByAsset[assets[idx].ID]; ok {
			assets[idx].CheckedOutTo = checkout.Customer
			assets[idx].CheckedOutAt = checkout.CheckedOut
			assets[idx].CheckoutCircuit = checkout.CircuitID
		}
		assets[idx].Source = source
	}

	s.data.Hardware = assets
	s.pushEvent(ActivityEvent{
		When:     time.Now().Format(time.RFC3339),
		Category: "hardware",
		Message:  fmt.Sprintf("Refreshed %d hardware assets from %s.", len(assets), source),
	})
	return s.persistLocked()
}

func (s *Store) CreateHardwareCheckoutDraft(input CreateCheckoutInput) (HardwareCheckoutDraft, error) {
	if strings.TrimSpace(input.AssetID) == "" || strings.TrimSpace(input.Customer) == "" {
		return HardwareCheckoutDraft{}, errors.New("assetId and customer are required")
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	assetIndex := -1
	for idx := range s.data.Hardware {
		if s.data.Hardware[idx].ID == input.AssetID {
			assetIndex = idx
			break
		}
	}
	if assetIndex == -1 {
		return HardwareCheckoutDraft{}, errors.New("hardware asset not found")
	}

	now := time.Now()
	draft := HardwareCheckoutDraft{
		ID:          fmt.Sprintf("hwdraft-%d", now.UnixNano()),
		AssetID:     strings.TrimSpace(input.AssetID),
		Customer:    strings.TrimSpace(input.Customer),
		CircuitID:   strings.TrimSpace(input.CircuitID),
		Notes:       strings.TrimSpace(input.Notes),
		RequestedBy: strings.TrimSpace(input.RequestedBy),
		Reason:      strings.TrimSpace(input.Reason),
		Status:      "pending-approval",
		SubmittedAt: now.Format(time.RFC3339),
	}
	s.pushEvent(ActivityEvent{
		When:     draft.SubmittedAt,
		Category: "draft",
		Message:  fmt.Sprintf("Queued hardware checkout draft for %s to %s.", s.data.Hardware[assetIndex].Name, draft.Customer),
	})
	s.data.HardwareCheckoutDrafts = append([]HardwareCheckoutDraft{draft}, s.data.HardwareCheckoutDrafts...)
	return draft, s.persistLocked()
}

func (s *Store) ApproveHardwareCheckoutDraft(id string, approvedBy string) (HardwareCheckoutDraft, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	for idx := range s.data.HardwareCheckoutDrafts {
		draft := &s.data.HardwareCheckoutDrafts[idx]
		if draft.ID != id {
			continue
		}

		assetIndex := -1
		for hidx := range s.data.Hardware {
			if s.data.Hardware[hidx].ID == draft.AssetID {
				assetIndex = hidx
				break
			}
		}
		if assetIndex == -1 {
			return HardwareCheckoutDraft{}, errors.New("hardware asset not found")
		}

		record := CheckoutRecord{
			AssetID:    draft.AssetID,
			Customer:   draft.Customer,
			CircuitID:  draft.CircuitID,
			CheckedOut: time.Now().Format(time.RFC3339),
			Notes:      draft.Notes,
		}

		replaced := false
		for cidx := range s.data.Checkouts {
			if s.data.Checkouts[cidx].AssetID == draft.AssetID {
				s.data.Checkouts[cidx] = record
				replaced = true
				break
			}
		}
		if !replaced {
			s.data.Checkouts = append([]CheckoutRecord{record}, s.data.Checkouts...)
		}

		s.data.Hardware[assetIndex].CheckedOutTo = record.Customer
		s.data.Hardware[assetIndex].CheckedOutAt = record.CheckedOut
		s.data.Hardware[assetIndex].CheckoutCircuit = record.CircuitID
		s.data.Hardware[assetIndex].Status = "checked-out"
		draft.Status = "approved"
		draft.ApprovedAt = record.CheckedOut
		draft.ApprovedBy = valueOr(strings.TrimSpace(approvedBy), "superuser")

		s.pushEvent(ActivityEvent{
			When:     draft.ApprovedAt,
			Category: "approval",
			Message:  fmt.Sprintf("Approved hardware checkout for %s to %s.", s.data.Hardware[assetIndex].Name, draft.Customer),
		})
		return *draft, s.persistLocked()
	}

	return HardwareCheckoutDraft{}, errors.New("hardware checkout draft not found")
}

func (s *Store) CreateSiteDraft(input CreateSiteDraftInput) (SiteDraft, error) {
	if strings.TrimSpace(input.SiteID) == "" {
		return SiteDraft{}, errors.New("siteId is required")
	}
	now := time.Now()
	draft := SiteDraft{
		ID:           fmt.Sprintf("draft-%d", now.UnixNano()),
		SiteID:       strings.TrimSpace(input.SiteID),
		DisplayName:  strings.TrimSpace(input.DisplayName),
		ServiceClass: strings.TrimSpace(input.ServiceClass),
		Notes:        strings.TrimSpace(input.Notes),
		RequestedBy:  strings.TrimSpace(input.RequestedBy),
		Reason:       strings.TrimSpace(input.Reason),
		Status:       "pending-approval",
		SubmittedAt:  now.Format(time.RFC3339),
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	s.data.SiteDrafts = append([]SiteDraft{draft}, s.data.SiteDrafts...)
	s.pushEvent(ActivityEvent{
		When:     draft.SubmittedAt,
		Category: "draft",
		Message:  fmt.Sprintf("Queued site overlay draft for %s by %s.", draft.SiteID, valueOr(draft.RequestedBy, "unknown")),
	})
	return draft, s.persistLocked()
}

func (s *Store) ApproveSiteDraft(id string, approvedBy string) (SiteDraft, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for idx := range s.data.SiteDrafts {
		draft := &s.data.SiteDrafts[idx]
		if draft.ID != id {
			continue
		}
		draft.Status = "approved"
		draft.ApprovedAt = time.Now().Format(time.RFC3339)
		draft.ApprovedBy = valueOr(strings.TrimSpace(approvedBy), "superuser")

		overlay := SiteOverlay{
			SiteID:         draft.SiteID,
			DisplayName:    draft.DisplayName,
			ServiceClass:   draft.ServiceClass,
			Notes:          draft.Notes,
			LastApprovedAt: draft.ApprovedAt,
		}
		replaced := false
		for oidx := range s.data.SiteOverlays {
			if s.data.SiteOverlays[oidx].SiteID == overlay.SiteID {
				s.data.SiteOverlays[oidx] = overlay
				replaced = true
				break
			}
		}
		if !replaced {
			s.data.SiteOverlays = append(s.data.SiteOverlays, overlay)
		}

		s.pushEvent(ActivityEvent{
			When:     draft.ApprovedAt,
			Category: "approval",
			Message:  fmt.Sprintf("Approved site overlay for %s.", draft.SiteID),
		})
		return *draft, s.persistLocked()
	}
	return SiteDraft{}, errors.New("draft not found")
}

func (s *Store) loadOrSeed() error {
	if err := os.MkdirAll(filepath.Dir(s.path), 0o755); err != nil {
		return err
	}

	raw, err := os.ReadFile(s.path)
	if err == nil {
		var state State
		if err := json.Unmarshal(raw, &state); err != nil {
			return err
		}
		s.data = state
		s.migrateLocked()
		return nil
	}
	if !errors.Is(err, os.ErrNotExist) {
		return err
	}

	s.data = seedState()
	return s.persistLocked()
}

func (s *Store) persistLocked() error {
	s.migrateLocked()
	raw, err := json.MarshalIndent(s.data, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(s.path, raw, 0o644)
}

func (s *Store) pushEvent(event ActivityEvent) {
	s.data.Events = append([]ActivityEvent{event}, s.data.Events...)
	if len(s.data.Events) > 20 {
		s.data.Events = s.data.Events[:20]
	}
}

func (s *Store) migrateLocked() {
	s.data.Billing = BillingOverview{}
	s.data.Changes = nil
	s.data.Findings = nil
	s.data.Network = NetworkView{}
	s.data.Summary.TopSignals = nil
	s.data.Config.BillingMode = ""
	if s.data.Config.Notes == "PPPoE is intentionally not the default workflow in this prototype." {
		s.data.Config.Notes = "Live operational data is preferred over seeded placeholders."
	}
	filteredSubscribers := make([]Subscriber, 0, len(s.data.Subscribers))
	for _, subscriber := range s.data.Subscribers {
		if strings.HasPrefix(subscriber.ID, "sub-") && subscriber.LastSeen == "awaiting first discover" {
			continue
		}
		filteredSubscribers = append(filteredSubscribers, subscriber)
	}
	s.data.Subscribers = filteredSubscribers
	filteredEvents := make([]ActivityEvent, 0, len(s.data.Events))
	for _, event := range s.data.Events {
		switch event.Category {
		case "hardware", "draft", "approval", "source":
			filteredEvents = append(filteredEvents, event)
		}
	}
	s.data.Events = filteredEvents
}

func seedState() State {
	return State{
		Summary: DashboardSummary{
			ProviderName: "Lynx Access",
			Region:       "Workspace-derived operational view",
		},
		Subscribers:            []Subscriber{},
		Network:                NetworkView{},
		Hardware:               []HardwareAsset{},
		Checkouts:              []CheckoutRecord{},
		HardwareCheckoutDrafts: []HardwareCheckoutDraft{},
		SiteOverlays:           []SiteOverlay{},
		SiteDrafts:             []SiteDraft{},
		Findings:               []Finding{},
		Changes:                []ChangePlan{},
		Billing:                BillingOverview{},
		Config: PlatformConfig{
			IdentityMode: "DHCP Option 82 first",
			AccessMode:   "Relay / VLAN / topology driven",
			Notes:        "Waiting on live sources or approved local drafts.",
		},
		Events: []ActivityEvent{},
	}
}

func valueOr(value, fallback string) string {
	if strings.TrimSpace(value) != "" {
		return value
	}
	return fallback
}
