package data

type DashboardSummary struct {
	ProviderName      string   `json:"providerName"`
	Region            string   `json:"region"`
	SubscribersTotal  int      `json:"subscribersTotal"`
	OnlineSubscribers int      `json:"onlineSubscribers"`
	ActiveRelays      int      `json:"activeRelays"`
	OpenFindings      int      `json:"openFindings"`
	CollectionRate    string   `json:"collectionRate"`
	TopSignals        []string `json:"topSignals"`
}

type OverviewSummary struct {
	ProviderName          string   `json:"providerName"`
	Region                string   `json:"region"`
	TenantCount           int      `json:"tenantCount"`
	HardwareCount         int      `json:"hardwareCount"`
	CheckedOutCount       int      `json:"checkedOutCount"`
	SiteCount             int      `json:"siteCount"`
	GraphNodeCount        int      `json:"graphNodeCount"`
	GraphEdgeCount        int      `json:"graphEdgeCount"`
	VersionDriftCount     int      `json:"versionDriftCount"`
	PortsNeedingAttention int      `json:"portsNeedingAttention"`
	RogueDeviceCount      int      `json:"rogueDeviceCount"`
	OltAnomalyCount       int      `json:"oltAnomalyCount"`
	PendingApprovalCount  int      `json:"pendingApprovalCount"`
	SourceNotes           []string `json:"sourceNotes"`
}

type Subscriber struct {
	ID             string  `json:"id"`
	Name           string  `json:"name"`
	Site           string  `json:"site"`
	Status         string  `json:"status"`
	Plan           string  `json:"plan"`
	CircuitID      string  `json:"circuitId"`
	RemoteID       string  `json:"remoteId"`
	Relay          string  `json:"relay"`
	VLAN           int     `json:"vlan"`
	IPv4           string  `json:"ipv4"`
	CPEMAC         string  `json:"cpeMac"`
	LastSeen       string  `json:"lastSeen"`
	SignalLabel    string  `json:"signalLabel"`
	MonthlyRevenue float64 `json:"monthlyRevenue"`
}

type RelayDomain struct {
	Name           string `json:"name"`
	AccessNode     string `json:"accessNode"`
	MgmtIP         string `json:"mgmtIp"`
	Site           string `json:"site"`
	Option82Policy string `json:"option82Policy"`
	Status         string `json:"status"`
	LastSnapshot   string `json:"lastSnapshot"`
}

type TopologyLink struct {
	Source string `json:"source"`
	Target string `json:"target"`
	Label  string `json:"label"`
	State  string `json:"state"`
}

type NetworkView struct {
	Relays []RelayDomain  `json:"relays"`
	Links  []TopologyLink `json:"links"`
}

type NetworkNode struct {
	Identity  string `json:"identity"`
	IP        string `json:"ip"`
	BoardName string `json:"boardName"`
	Version   string `json:"version"`
	SiteID    string `json:"siteId"`
	Role      string `json:"role"`
}

type VersionBucket struct {
	Version string `json:"version"`
	Count   int    `json:"count"`
}

type SiteStats struct {
	SiteID          string `json:"siteId"`
	DisplayName     string `json:"displayName"`
	Notes           string `json:"notes,omitempty"`
	ServiceClass    string `json:"serviceClass,omitempty"`
	HardwareCount   int    `json:"hardwareCount"`
	GraphNodeCount  int    `json:"graphNodeCount"`
	CheckedOutCount int    `json:"checkedOutCount"`
	RouterCount     int    `json:"routerCount"`
	SwitchCount     int    `json:"switchCount"`
	AttentionPorts  int    `json:"attentionPorts"`
	RogueDevices    int    `json:"rogueDevices"`
}

type NetworkGraph struct {
	SourcePath     string          `json:"sourcePath"`
	ScanID         int             `json:"scanId"`
	NodeCount      int             `json:"nodeCount"`
	EdgeCount      int             `json:"edgeCount"`
	LatestVersion  string          `json:"latestVersion"`
	VersionBuckets []VersionBucket `json:"versionBuckets"`
	DriftDevices   []NetworkNode   `json:"driftDevices"`
	Sites          []SiteStats     `json:"sites"`
	EdgesPreview   []TopologyLink  `json:"edgesPreview"`
}

type Finding struct {
	ID         string `json:"id"`
	Severity   string `json:"severity"`
	Title      string `json:"title"`
	Device     string `json:"device"`
	Evidence   string `json:"evidence"`
	NextAction string `json:"nextAction"`
	Status     string `json:"status"`
	AckedAt    string `json:"ackedAt,omitempty"`
}

type BillingOverview struct {
	Processor          string   `json:"processor"`
	DepositAccount     string   `json:"depositAccount"`
	AutoPayEnabled     int      `json:"autoPayEnabled"`
	QueuedInvoices     int      `json:"queuedInvoices"`
	SettlementWindow   string   `json:"settlementWindow"`
	DefaultWorkstreams []string `json:"defaultWorkstreams"`
}

type ChangePlan struct {
	ID           string `json:"id"`
	Window       string `json:"window"`
	Scope        string `json:"scope"`
	Risk         string `json:"risk"`
	Status       string `json:"status"`
	Verification string `json:"verification"`
	ApprovedAt   string `json:"approvedAt,omitempty"`
}

type PlatformConfig struct {
	IdentityMode string `json:"identityMode"`
	BillingMode  string `json:"billingMode"`
	AccessMode   string `json:"accessMode"`
	Notes        string `json:"notes"`
}

type ActivityEvent struct {
	When     string `json:"when"`
	Category string `json:"category"`
	Message  string `json:"message"`
}

type Customer struct {
	ID          int    `json:"id"`
	Name        string `json:"name"`
	Slug        string `json:"slug"`
	Description string `json:"description"`
	Comments    string `json:"comments"`
}

type DataSourceStatus struct {
	Name       string `json:"name"`
	Path       string `json:"path"`
	UpdatedAt  string `json:"updatedAt"`
	RecordHint string `json:"recordHint"`
	Status     string `json:"status"`
}

type AttentionPort struct {
	Identity   string   `json:"identity"`
	IP         string   `json:"ip"`
	SiteID     string   `json:"siteId"`
	Interface  string   `json:"interface"`
	Status     string   `json:"status"`
	Comment    string   `json:"comment"`
	PVID       string   `json:"pvid"`
	HostCount  int      `json:"hostCount"`
	Issues     []string `json:"issues"`
	Fixes      []string `json:"fixes"`
	LastLinkUp string   `json:"lastLinkUp"`
	LinkDowns  string   `json:"linkDowns"`
}

type RogueDevice struct {
	Identity  string   `json:"identity"`
	IP        string   `json:"ip"`
	SiteID    string   `json:"siteId"`
	Interface string   `json:"interface"`
	MAC       string   `json:"mac"`
	VLAN      string   `json:"vlan"`
	Address   string   `json:"address,omitempty"`
	Reasons   []string `json:"reasons"`
	Source    string   `json:"source"`
}

type OltAnomaly struct {
	Severity    string  `json:"severity"`
	Interface   string  `json:"interface"`
	Signal      string  `json:"signal"`
	LikelyScope string  `json:"likelyScope"`
	Confidence  float64 `json:"confidence"`
}

type OltSnapshot struct {
	Identity       string       `json:"identity"`
	BoardName      string       `json:"boardName"`
	Version        string       `json:"version"`
	CollectedAt    string       `json:"collectedAt"`
	RunningLinks   int          `json:"runningLinks"`
	MonitoredLinks int          `json:"monitoredLinks"`
	Anomalies      []OltAnomaly `json:"anomalies"`
}

type OperationalSummary struct {
	Sources               []DataSourceStatus `json:"sources"`
	PortsTotal            int                `json:"portsTotal"`
	PortsNeedingAttention int                `json:"portsNeedingAttention"`
	AttentionPorts        []AttentionPort    `json:"attentionPorts"`
	RogueDevices          []RogueDevice      `json:"rogueDevices"`
	Olt                   OltSnapshot        `json:"olt"`
}

type SiteOverlay struct {
	SiteID         string `json:"siteId"`
	DisplayName    string `json:"displayName"`
	ServiceClass   string `json:"serviceClass"`
	Notes          string `json:"notes"`
	LastApprovedAt string `json:"lastApprovedAt,omitempty"`
}

type SiteDraft struct {
	ID           string `json:"id"`
	SiteID       string `json:"siteId"`
	DisplayName  string `json:"displayName"`
	ServiceClass string `json:"serviceClass"`
	Notes        string `json:"notes"`
	RequestedBy  string `json:"requestedBy"`
	Reason       string `json:"reason"`
	Status       string `json:"status"`
	SubmittedAt  string `json:"submittedAt"`
	ApprovedAt   string `json:"approvedAt,omitempty"`
	ApprovedBy   string `json:"approvedBy,omitempty"`
}

type HardwareCheckoutDraft struct {
	ID          string `json:"id"`
	AssetID     string `json:"assetId"`
	Customer    string `json:"customer"`
	CircuitID   string `json:"circuitId"`
	Notes       string `json:"notes"`
	RequestedBy string `json:"requestedBy"`
	Reason      string `json:"reason"`
	Status      string `json:"status"`
	SubmittedAt string `json:"submittedAt"`
	ApprovedAt  string `json:"approvedAt,omitempty"`
	ApprovedBy  string `json:"approvedBy,omitempty"`
}

type CreateSiteDraftInput struct {
	SiteID       string `json:"siteId"`
	DisplayName  string `json:"displayName"`
	ServiceClass string `json:"serviceClass"`
	Notes        string `json:"notes"`
	RequestedBy  string `json:"requestedBy"`
	Reason       string `json:"reason"`
}

type ApproveDraftInput struct {
	ApprovalKey string `json:"approvalKey"`
	ApprovedBy  string `json:"approvedBy"`
}
