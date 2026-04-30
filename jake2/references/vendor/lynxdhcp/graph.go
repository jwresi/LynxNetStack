package workspace

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"lynxdhcp/internal/data"
)

type graphFile struct {
	ScanID int         `json:"scan_id"`
	Nodes  []graphNode `json:"nodes"`
	Edges  []graphEdge `json:"edges"`
}

type graphNode struct {
	IP        string `json:"ip"`
	Identity  string `json:"identity"`
	BoardName string `json:"board_name"`
	Version   string `json:"version"`
	IsCRS     bool   `json:"is_crs"`
}

type graphEdge struct {
	FromIP        string `json:"from_ip"`
	FromInterface string `json:"from_interface"`
	ToIdentity    string `json:"to_identity"`
	ToAddress     string `json:"to_address"`
}

func KnownGraphPaths() []string {
	return []string{
		"<legacy sibling repo>/network_graph_latest.json",
		"<legacy sibling repo>/network_graph_latest.json",
	}
}

func LoadGraph(overlays []data.SiteOverlay, hardware []data.HardwareAsset) (data.NetworkGraph, error) {
	path := ""
	for _, candidate := range KnownGraphPaths() {
		if _, err := os.Stat(candidate); err == nil {
			path = candidate
			break
		}
	}
	if path == "" {
		return data.NetworkGraph{}, fmt.Errorf("network graph not found")
	}

	raw, err := os.ReadFile(path)
	if err != nil {
		return data.NetworkGraph{}, err
	}

	var payload graphFile
	if err := json.Unmarshal(raw, &payload); err != nil {
		return data.NetworkGraph{}, err
	}

	overlayBySite := map[string]data.SiteOverlay{}
	for _, overlay := range overlays {
		overlayBySite[overlay.SiteID] = overlay
	}

	versionCounts := map[string]int{}
	siteStats := map[string]*data.SiteStats{}
	graphNodes := make([]data.NetworkNode, 0, len(payload.Nodes))
	latestVersion := ""
	for _, node := range payload.Nodes {
		siteID := normalizeSiteID(extractSiteID(node.Identity))
		role := "router"
		if node.IsCRS {
			role = "switch"
		}
		graphNodes = append(graphNodes, data.NetworkNode{
			Identity:  node.Identity,
			IP:        node.IP,
			BoardName: node.BoardName,
			Version:   node.Version,
			SiteID:    siteID,
			Role:      role,
		})
		versionCounts[node.Version]++
		if compareVersions(node.Version, latestVersion) > 0 {
			latestVersion = node.Version
		}

		stats := ensureSiteStat(siteStats, overlayBySite, siteID)
		stats.GraphNodeCount++
		if role == "router" {
			stats.RouterCount++
		} else {
			stats.SwitchCount++
		}
	}

	for _, asset := range hardware {
		siteID := normalizeSiteID(asset.Site)
		stats := ensureSiteStat(siteStats, overlayBySite, siteID)
		stats.HardwareCount++
		if asset.CheckedOutTo != "" {
			stats.CheckedOutCount++
		}
	}

	drift := make([]data.NetworkNode, 0)
	for _, node := range graphNodes {
		if latestVersion != "" && compareVersions(node.Version, latestVersion) < 0 {
			drift = append(drift, node)
		}
	}
	sort.Slice(drift, func(i, j int) bool {
		if drift[i].Version == drift[j].Version {
			return drift[i].Identity < drift[j].Identity
		}
		return compareVersions(drift[i].Version, drift[j].Version) < 0
	})
	if len(drift) > 15 {
		drift = drift[:15]
	}

	buckets := make([]data.VersionBucket, 0, len(versionCounts))
	for version, count := range versionCounts {
		buckets = append(buckets, data.VersionBucket{Version: version, Count: count})
	}
	sort.Slice(buckets, func(i, j int) bool {
		if buckets[i].Count == buckets[j].Count {
			return compareVersions(buckets[i].Version, buckets[j].Version) > 0
		}
		return buckets[i].Count > buckets[j].Count
	})

	sites := make([]data.SiteStats, 0, len(siteStats))
	for _, stats := range siteStats {
		sites = append(sites, *stats)
	}
	sort.Slice(sites, func(i, j int) bool { return sites[i].SiteID < sites[j].SiteID })

	preview := make([]data.TopologyLink, 0, min(12, len(payload.Edges)))
	for _, edge := range payload.Edges[:min(12, len(payload.Edges))] {
		preview = append(preview, data.TopologyLink{
			Source: edge.FromIP,
			Target: edge.ToIdentity,
			Label:  edge.FromInterface,
			State:  "up",
		})
	}

	return data.NetworkGraph{
		SourcePath:     path,
		ScanID:         payload.ScanID,
		NodeCount:      len(payload.Nodes),
		EdgeCount:      len(payload.Edges),
		LatestVersion:  latestVersion,
		VersionBuckets: buckets,
		DriftDevices:   drift,
		Sites:          sites,
		EdgesPreview:   preview,
	}, nil
}

func ensureSiteStat(siteStats map[string]*data.SiteStats, overlays map[string]data.SiteOverlay, siteID string) *data.SiteStats {
	if current, ok := siteStats[siteID]; ok {
		return current
	}
	display := siteID
	notes := ""
	serviceClass := ""
	if overlay, ok := overlays[siteID]; ok {
		display = valueOr(overlay.DisplayName, siteID)
		notes = overlay.Notes
		serviceClass = overlay.ServiceClass
	}
	stats := &data.SiteStats{
		SiteID:       siteID,
		DisplayName:  display,
		Notes:        notes,
		ServiceClass: serviceClass,
	}
	siteStats[siteID] = stats
	return stats
}

func extractSiteID(identity string) string {
	if identity == "" {
		return "unknown"
	}
	parts := strings.Split(identity, ".")
	if len(parts) > 0 && len(parts[0]) >= 4 {
		return parts[0]
	}
	return identity
}

func compareVersions(a, b string) int {
	parse := func(input string) [3]int {
		input = strings.TrimSpace(strings.Split(input, " ")[0])
		var out [3]int
		var cur int
		var idx int
		for _, r := range input {
			if r >= '0' && r <= '9' {
				cur = cur*10 + int(r-'0')
				continue
			}
			if r == '.' {
				if idx < len(out) {
					out[idx] = cur
				}
				idx++
				cur = 0
			}
		}
		if idx < len(out) {
			out[idx] = cur
		}
		return out
	}
	pa := parse(a)
	pb := parse(b)
	for i := 0; i < len(pa); i++ {
		if pa[i] > pb[i] {
			return 1
		}
		if pa[i] < pb[i] {
			return -1
		}
	}
	return strings.Compare(filepath.Base(a), filepath.Base(b))
}

func valueOr(value, fallback string) string {
	if strings.TrimSpace(value) != "" {
		return value
	}
	return fallback
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
