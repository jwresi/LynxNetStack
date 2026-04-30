package workspace

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"lynxdhcp/internal/data"
)

type customerPortMapFile struct {
	Summary struct {
		PortsTotal            int `json:"ports_total"`
		PortsNeedingAttention int `json:"ports_needing_attention"`
	} `json:"summary"`
	Ports []struct {
		Identity       string   `json:"identity"`
		IP             string   `json:"ip"`
		Interface      string   `json:"interface"`
		Status         string   `json:"status"`
		Comment        string   `json:"comment"`
		PVID           string   `json:"pvid"`
		HostCount      int      `json:"host_count"`
		Issues         []string `json:"issues"`
		Fixes          []string `json:"fixes"`
		LastLinkUpTime string   `json:"last_link_up_time"`
		LinkDowns      string   `json:"link_downs"`
	} `json:"ports"`
}

type rogueOutlierFile struct {
	SwitchHits []struct {
		Identity    string   `json:"identity"`
		IP          string   `json:"ip"`
		OnInterface string   `json:"on_interface"`
		MAC         string   `json:"mac"`
		VID         string   `json:"vid"`
		Reasons     []string `json:"reasons"`
	} `json:"switch_hits"`
	RouterHits []struct {
		Identity  string   `json:"identity"`
		IP        string   `json:"ip"`
		Interface string   `json:"interface"`
		MAC       string   `json:"mac"`
		Address   string   `json:"address"`
		Reasons   []string `json:"reasons"`
	} `json:"router_hits"`
}

type oltBaselineFile struct {
	CollectedAt string `json:"collected_at"`
	Identity    string `json:"identity"`
	Resource    struct {
		BoardName string `json:"board-name"`
		Version   string `json:"version"`
	} `json:"resource"`
	Interfaces []struct {
		Name    string `json:"name"`
		Running string `json:"running"`
	} `json:"interfaces"`
}

type oltAnomalyFile struct {
	Anomalies []struct {
		Severity    string  `json:"severity"`
		Interface   string  `json:"interface"`
		Signal      string  `json:"signal"`
		LikelyScope string  `json:"likely_scope"`
		Confidence  float64 `json:"confidence"`
	} `json:"anomalies"`
}

func LoadOperationalSummary() (data.OperationalSummary, error) {
	portMapPath, err := firstExistingPath(
		"<legacy sibling repo>/artifacts/customer_port_map/customer_port_map.json",
		"<legacy sibling repo>/artifacts/customer_port_map/customer_port_map.json",
	)
	if err != nil {
		return data.OperationalSummary{}, err
	}
	roguePath, _ := firstExistingPath(
		"<legacy sibling repo>/artifacts/rogue_customer_outliers/rogue_customer_outliers.json",
		"<legacy sibling repo>/artifacts/rogue_customer_outliers/rogue_customer_outliers.json",
	)
	oltDir, _ := latestMatchingDir(
		"<legacy sibling repo>/artifacts/olt_audit_*",
		"<legacy sibling repo>/artifacts/olt_audit_*",
	)

	sources := make([]data.DataSourceStatus, 0, 4)
	var portMap customerPortMapFile
	if err := loadJSON(portMapPath, &portMap); err != nil {
		return data.OperationalSummary{}, err
	}
	sources = append(sources, sourceStatus("customer port map", portMapPath, fmt.Sprintf("%d ports", portMap.Summary.PortsTotal)))

	attention := make([]data.AttentionPort, 0, portMap.Summary.PortsNeedingAttention)
	for _, port := range portMap.Ports {
		if port.Status == "clean" || port.Status == "expected_exception" {
			continue
		}
		attention = append(attention, data.AttentionPort{
			Identity:   port.Identity,
			IP:         port.IP,
			SiteID:     normalizeSiteID(extractSiteID(port.Identity)),
			Interface:  port.Interface,
			Status:     port.Status,
			Comment:    port.Comment,
			PVID:       port.PVID,
			HostCount:  port.HostCount,
			Issues:     port.Issues,
			Fixes:      port.Fixes,
			LastLinkUp: port.LastLinkUpTime,
			LinkDowns:  port.LinkDowns,
		})
	}
	sort.Slice(attention, func(i, j int) bool {
		if attention[i].SiteID == attention[j].SiteID {
			if attention[i].Identity == attention[j].Identity {
				return attention[i].Interface < attention[j].Interface
			}
			return attention[i].Identity < attention[j].Identity
		}
		return attention[i].SiteID < attention[j].SiteID
	})
	if len(attention) > 24 {
		attention = attention[:24]
	}

	rogues := make([]data.RogueDevice, 0)
	if roguePath != "" {
		var rogue rogueOutlierFile
		if err := loadJSON(roguePath, &rogue); err == nil {
			sources = append(sources, sourceStatus("rogue outliers", roguePath, fmt.Sprintf("%d hits", len(rogue.SwitchHits)+len(rogue.RouterHits))))
			for _, hit := range rogue.SwitchHits {
				rogues = append(rogues, data.RogueDevice{
					Identity:  hit.Identity,
					IP:        hit.IP,
					SiteID:    normalizeSiteID(extractSiteID(hit.Identity)),
					Interface: hit.OnInterface,
					MAC:       hit.MAC,
					VLAN:      hit.VID,
					Reasons:   hit.Reasons,
					Source:    "switch",
				})
			}
			for _, hit := range rogue.RouterHits {
				rogues = append(rogues, data.RogueDevice{
					Identity:  hit.Identity,
					IP:        hit.IP,
					SiteID:    normalizeSiteID(extractSiteID(hit.Identity)),
					Interface: hit.Interface,
					MAC:       hit.MAC,
					Address:   hit.Address,
					Reasons:   hit.Reasons,
					Source:    "router",
				})
			}
		}
	}
	sort.Slice(rogues, func(i, j int) bool {
		if rogues[i].SiteID == rogues[j].SiteID {
			if rogues[i].Identity == rogues[j].Identity {
				return rogues[i].MAC < rogues[j].MAC
			}
			return rogues[i].Identity < rogues[j].Identity
		}
		return rogues[i].SiteID < rogues[j].SiteID
	})
	if len(rogues) > 24 {
		rogues = rogues[:24]
	}

	olt := data.OltSnapshot{}
	if oltDir != "" {
		baselinePath := filepath.Join(oltDir, "baseline_snapshot.json")
		anomalyPath := filepath.Join(oltDir, "anomaly_deepdive.json")
		var baseline oltBaselineFile
		if err := loadJSON(baselinePath, &baseline); err == nil {
			var anomaly oltAnomalyFile
			_ = loadJSON(anomalyPath, &anomaly)

			runningLinks := 0
			monitored := 0
			for _, iface := range baseline.Interfaces {
				if strings.HasPrefix(iface.Name, "sfp-sfpplus") || iface.Name == "ether1" {
					monitored++
				}
				if iface.Running == "True" {
					runningLinks++
				}
			}
			olt = data.OltSnapshot{
				Identity:       baseline.Identity,
				BoardName:      baseline.Resource.BoardName,
				Version:        baseline.Resource.Version,
				CollectedAt:    baseline.CollectedAt,
				RunningLinks:   runningLinks,
				MonitoredLinks: monitored,
			}
			for _, item := range anomaly.Anomalies {
				olt.Anomalies = append(olt.Anomalies, data.OltAnomaly{
					Severity:    item.Severity,
					Interface:   item.Interface,
					Signal:      item.Signal,
					LikelyScope: item.LikelyScope,
					Confidence:  item.Confidence,
				})
			}
			sources = append(sources, sourceStatus("olt audit", baselinePath, baseline.Identity))
		}
	}

	return data.OperationalSummary{
		Sources:               sources,
		PortsTotal:            portMap.Summary.PortsTotal,
		PortsNeedingAttention: portMap.Summary.PortsNeedingAttention,
		AttentionPorts:        attention,
		RogueDevices:          rogues,
		Olt:                   olt,
	}, nil
}

func SiteAttentionCounts(ops data.OperationalSummary) (map[string]int, map[string]int) {
	portCounts := map[string]int{}
	rogueCounts := map[string]int{}
	for _, port := range ops.AttentionPorts {
		portCounts[port.SiteID]++
	}
	for _, rogue := range ops.RogueDevices {
		rogueCounts[rogue.SiteID]++
	}
	return portCounts, rogueCounts
}

func firstExistingPath(paths ...string) (string, error) {
	for _, candidate := range paths {
		if _, err := os.Stat(candidate); err == nil {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("required workspace artifact not found")
}

func latestMatchingDir(patterns ...string) (string, error) {
	type candidate struct {
		path string
		mod  time.Time
	}
	var matches []candidate
	for _, pattern := range patterns {
		paths, _ := filepath.Glob(pattern)
		for _, path := range paths {
			info, err := os.Stat(path)
			if err == nil && info.IsDir() {
				matches = append(matches, candidate{path: path, mod: info.ModTime()})
			}
		}
	}
	if len(matches) == 0 {
		return "", fmt.Errorf("no matching directories")
	}
	sort.Slice(matches, func(i, j int) bool { return matches[i].mod.After(matches[j].mod) })
	return matches[0].path, nil
}

func loadJSON(path string, out any) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(raw, out)
}

func sourceStatus(name, path, hint string) data.DataSourceStatus {
	info, err := os.Stat(path)
	if err != nil {
		return data.DataSourceStatus{Name: name, Path: path, RecordHint: hint, Status: "missing"}
	}
	return data.DataSourceStatus{
		Name:       name,
		Path:       path,
		UpdatedAt:  info.ModTime().Format(time.RFC3339),
		RecordHint: hint,
		Status:     "ready",
	}
}

func normalizeSiteID(siteID string) string {
	siteID = strings.TrimSpace(siteID)
	if siteID == "" {
		return "unknown"
	}
	numeric := true
	for _, r := range siteID {
		if r < '0' || r > '9' {
			numeric = false
			break
		}
	}
	if numeric && len(siteID) < 6 {
		return fmt.Sprintf("%06s", siteID)
	}
	return siteID
}
