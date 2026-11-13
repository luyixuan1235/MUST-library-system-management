import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ApiConfig {
  static const String _compiledDefault = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://172.20.10.10:8000',
  );

  static String? customBaseUrl;

  /// Dynamically resolves the backend base URL:
  /// 1. User-configured runtime override (SharedPreferences / Login page dialog)
  /// 2. On Flutter Web: automatically uses the host IP where the web page was opened
  /// 3. On Desktop/Mobile: uses the LAN Wi-Fi IP (with automatic localhost fallback)
  static String get baseUrl {
    if (customBaseUrl != null && customBaseUrl!.trim().isNotEmpty) {
      return customBaseUrl!.trim().replaceAll(RegExp(r'/+$'), '');
    }
    if (kIsWeb) {
      final host = Uri.base.host;
      final scheme = Uri.base.scheme.startsWith('http') ? Uri.base.scheme : 'http';
      if (host.isNotEmpty) {
        return '$scheme://$host:8000';
      }
    }
    return _compiledDefault;
  }

  static String get currentBaseUrl => baseUrl;

  static Future<void> loadSavedBaseUrl() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getString('custom_base_url');
      if (saved != null && saved.trim().isNotEmpty) {
        customBaseUrl = saved.trim();
      }
    } catch (_) {}
  }

  static Future<void> setCustomBaseUrl(String? url) async {
    customBaseUrl = (url != null && url.trim().isNotEmpty)
        ? url.trim().replaceAll(RegExp(r'/+$'), '')
        : null;
    try {
      final prefs = await SharedPreferences.getInstance();
      if (customBaseUrl == null) {
        await prefs.remove('custom_base_url');
      } else {
        await prefs.setString('custom_base_url', customBaseUrl!);
      }
    } catch (_) {}
  }
}
