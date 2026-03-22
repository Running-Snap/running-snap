import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Modal, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { apiGetMe, apiListAnalysisJobs, apiListShortformJobs, clearToken } from '@/constants/api';

type UserInfo = { username: string; email: string; created_at: string };

export default function ProfileScreen() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [analysisCount, setAnalysisCount] = useState(0);
  const [shortformCount, setShortformCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      apiGetMe(),
      apiListAnalysisJobs(),
      apiListShortformJobs(),
    ])
      .then(([me, analysis, shortforms]) => {
        setUser(me);
        setAnalysisCount(analysis.filter(j => j.status === 'done').length);
        setShortformCount(shortforms.filter(j => j.status === 'done').length);
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

  const handleLogout = () => {
    setShowLogoutConfirm(true);
  };

  const confirmLogout = async () => {
    await clearToken();
    router.replace('/login');
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#007AFF" />
      </View>
    );
  }

  const joinDate = user?.created_at
    ? new Date(user.created_at).toLocaleDateString('ko-KR')
    : '';

  return (
    <ScrollView style={styles.container}>
      <View style={styles.profileHeader}>
        <View style={styles.avatarCircle}>
          <Text style={styles.avatarText}>
            {(user?.username ?? '?').charAt(0).toUpperCase()}
          </Text>
        </View>
        <Text style={styles.userName}>{user?.username ?? '-'}</Text>
        <Text style={styles.userEmail}>{user?.email ?? '-'}</Text>
        {joinDate ? <Text style={styles.joinDate}>가입일: {joinDate}</Text> : null}
      </View>

      <View style={styles.statsRow}>
        <TouchableOpacity style={styles.statCard} onPress={() => router.push('/history')}>
          <Text style={styles.statNumber}>{analysisCount}</Text>
          <Text style={styles.statLabel}>분석 기록</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.statCard} onPress={() => router.push('/shortform-list')}>
          <Text style={styles.statNumber}>{shortformCount}</Text>
          <Text style={styles.statLabel}>내 숏폼</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.menuSection}>
        <Text style={styles.menuSectionTitle}>기록</Text>
        <TouchableOpacity style={styles.menuItem} onPress={() => router.push('/history')}>
          <Text style={styles.menuIcon}>📋</Text>
          <Text style={styles.menuText}>분석 기록</Text>
          <Text style={styles.menuArrow}>›</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.menuItem} onPress={() => router.push('/shortform-list')}>
          <Text style={styles.menuIcon}>🎬</Text>
          <Text style={styles.menuText}>내 숏폼</Text>
          <Text style={styles.menuArrow}>›</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.menuItem} onPress={() => router.push('/best-cut-history')}>
          <Text style={styles.menuIcon}>📸</Text>
          <Text style={styles.menuText}>베스트 컷</Text>
          <Text style={styles.menuArrow}>›</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.menuSection}>
        <Text style={styles.menuSectionTitle}>앱 정보</Text>
        <View style={styles.menuItem}>
          <Text style={styles.menuIcon}>ℹ️</Text>
          <Text style={styles.menuText}>앱 버전</Text>
          <Text style={styles.menuValue}>1.0.0</Text>
        </View>
      </View>

      <View style={styles.logoutSection}>
        <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
          <Text style={styles.logoutText}>로그아웃</Text>
        </TouchableOpacity>
      </View>

      {/* 로그아웃 확인 모달 */}
      <Modal
        visible={showLogoutConfirm}
        transparent
        animationType="fade"
        onRequestClose={() => setShowLogoutConfirm(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalBox}>
            <Text style={styles.modalTitle}>로그아웃</Text>
            <Text style={styles.modalMessage}>정말 로그아웃 하시겠어요?</Text>
            <View style={styles.modalButtons}>
              <TouchableOpacity
                style={styles.modalCancelButton}
                onPress={() => setShowLogoutConfirm(false)}
              >
                <Text style={styles.modalCancelText}>취소</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.modalConfirmButton}
                onPress={confirmLogout}
              >
                <Text style={styles.modalConfirmText}>로그아웃</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8f9fa' },
  loadingContainer: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  profileHeader: {
    backgroundColor: '#fff', alignItems: 'center',
    paddingTop: 60, paddingBottom: 32, borderBottomWidth: 1, borderBottomColor: '#f0f0f0',
  },
  avatarCircle: {
    width: 80, height: 80, borderRadius: 40, backgroundColor: '#007AFF',
    alignItems: 'center', justifyContent: 'center', marginBottom: 16,
  },
  avatarText: { fontSize: 32, fontWeight: 'bold', color: '#fff' },
  userName: { fontSize: 22, fontWeight: 'bold', color: '#000', marginBottom: 4 },
  userEmail: { fontSize: 14, color: '#666', marginBottom: 4 },
  joinDate: { fontSize: 13, color: '#aaa' },
  statsRow: { flexDirection: 'row', padding: 16, gap: 12 },
  statCard: {
    flex: 1, backgroundColor: '#fff', borderRadius: 12, padding: 20, alignItems: 'center',
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2,
  },
  statNumber: { fontSize: 28, fontWeight: 'bold', color: '#007AFF', marginBottom: 4 },
  statLabel: { fontSize: 13, color: '#666' },
  menuSection: {
    marginHorizontal: 16, marginBottom: 16, backgroundColor: '#fff', borderRadius: 12, overflow: 'hidden',
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2,
  },
  menuSectionTitle: {
    fontSize: 13, fontWeight: '600', color: '#999',
    paddingHorizontal: 16, paddingTop: 14, paddingBottom: 6, textTransform: 'uppercase',
  },
  menuItem: {
    flexDirection: 'row', alignItems: 'center',
    paddingVertical: 14, paddingHorizontal: 16, borderTopWidth: 1, borderTopColor: '#f5f5f5',
  },
  menuIcon: { fontSize: 20, marginRight: 12 },
  menuText: { flex: 1, fontSize: 16, color: '#000' },
  menuArrow: { fontSize: 20, color: '#ccc' },
  menuValue: { fontSize: 14, color: '#999' },
  logoutSection: { padding: 16, marginBottom: 32 },
  logoutButton: {
    backgroundColor: '#fff', borderRadius: 12, padding: 16,
    alignItems: 'center', borderWidth: 1, borderColor: '#FF3B30',
  },
  logoutText: { fontSize: 16, fontWeight: 'bold', color: '#FF3B30' },
  modalOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center', alignItems: 'center',
  },
  modalBox: {
    backgroundColor: '#fff', borderRadius: 16, padding: 24,
    width: '80%', alignItems: 'center',
  },
  modalTitle: { fontSize: 18, fontWeight: 'bold', color: '#000', marginBottom: 8 },
  modalMessage: { fontSize: 15, color: '#666', marginBottom: 24 },
  modalButtons: { flexDirection: 'row', gap: 12, width: '100%' },
  modalCancelButton: {
    flex: 1, backgroundColor: '#f0f0f0', borderRadius: 10,
    padding: 14, alignItems: 'center',
  },
  modalCancelText: { fontSize: 15, fontWeight: '600', color: '#666' },
  modalConfirmButton: {
    flex: 1, backgroundColor: '#FF3B30', borderRadius: 10,
    padding: 14, alignItems: 'center',
  },
  modalConfirmText: { fontSize: 15, fontWeight: '600', color: '#fff' },
});
