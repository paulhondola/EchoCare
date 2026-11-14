// Copy to arduino_secrets.h (git-ignored) and fill in. Ecou serves this network
// from its Linux side (08-ecou.md §2.6), e.g.:
//   nmcli device wifi hotspot ifname wlan0 ssid Ecou password 'ecou-acasa'
#define SECRET_SSID "Ecou"
#define SECRET_PASS "ecou-acasa"
// The same value as ECOU_PUIUL_KEY in Ecou's app environment; any long random text
#define SECRET_LINK_KEY "change-me-to-a-long-random-text"
