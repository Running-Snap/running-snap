import { router } from 'expo-router';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

export default function HomeScreen() {
  return (
    <ScrollView style={styles.container}>

      {/* 헤더 */}
      <View style={styles.header}>
        <Text style={styles.welcomeText}>환영합니다! 👋</Text>
        <Text style={styles.subtitle}>오늘도 달려볼까요?</Text>
      </View>

      {/* 메인 기능 버튼 2개 */}
      <View style={styles.mainButtons}>
        <TouchableOpacity
          style={[styles.mainButton, styles.analyzeButton]}
          onPress={() => router.push('/analyze-video')}
        >
          <Text style={styles.mainButtonIcon}>🎥</Text>
          <Text style={styles.mainButtonTitle}>영상 분석하기</Text>
          <Text style={styles.mainButtonSubtitle}>AI가 자세를 분석해드려요</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.mainButton, styles.shortformButton]}
          onPress={() => router.push('/create-shortform')}
        >
          <Text style={styles.mainButtonIcon}>✨</Text>
          <Text style={styles.mainButtonTitle}>숏폼 만들기</Text>
          <Text style={styles.mainButtonSubtitle}>여러 영상을 하나로 편집</Text>
        </TouchableOpacity>
        {/* 베스트 컷 추출 (신규) */}
        <TouchableOpacity
          style={[styles.mainButton, styles.bestCutButton]}
          onPress={() => router.push('/best-cut')}
        >
          <Text style={styles.mainButtonIcon}>📸</Text>
          <Text style={styles.mainButtonTitle}>베스트 컷 추출</Text>
          <Text style={styles.mainButtonSubtitle}>AI가 최고의 순간을 찾아드려요</Text>
        </TouchableOpacity>
      </View>

      {/* 기록 섹션 */}
      <View style={styles.section}>

        {/* 최근 분석 기록 */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>최근 분석 기록</Text>
          <TouchableOpacity onPress={() => router.push('/history')}>
            <Text style={styles.seeAllButton}>전체 보기 ›</Text>
          </TouchableOpacity>
        </View>
        <TouchableOpacity
          style={styles.recordPreviewCard}
          onPress={() => router.push('/history')}
        >
          <Text style={styles.emptyStateText}>📋 분석 기록 보러가기</Text>
          <Text style={styles.arrowIcon}>›</Text>
        </TouchableOpacity>

        {/* 숏폼 기록 */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>내 숏폼</Text>
          <TouchableOpacity onPress={() => router.push('/shortform-list')}>
            <Text style={styles.seeAllButton}>전체 보기 ›</Text>
          </TouchableOpacity>
        </View>
        <TouchableOpacity
          style={styles.recordPreviewCard}
          onPress={() => router.push('/shortform-list')}
        >
          <Text style={styles.emptyStateText}>🎬 숏폼 기록 보러가기</Text>
          <Text style={styles.arrowIcon}>›</Text>
        </TouchableOpacity>
        {/* 베스트 컷 기록 (신규) */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>베스트 컷</Text>
          <TouchableOpacity onPress={() => router.push('/best-cut-history')}>
            <Text style={styles.seeAllButton}>전체 보기 ›</Text>
          </TouchableOpacity>
        </View>
        <TouchableOpacity
          style={styles.recordPreviewCard}
          onPress={() => router.push('/best-cut-history')}
        >
          <Text style={styles.emptyStateText}>📸 베스트 컷 보러가기</Text>
          <Text style={styles.arrowIcon}>›</Text>
        </TouchableOpacity>

        {/* 내 영상 (카메라 매칭) */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>내 영상</Text>
          <TouchableOpacity onPress={() => router.push('/my-clips')}>
            <Text style={styles.seeAllButton}>전체 보기 ›</Text>
          </TouchableOpacity>
        </View>
        <TouchableOpacity
          style={styles.recordPreviewCard}
          onPress={() => router.push('/my-clips')}
        >
          <Text style={styles.emptyStateText}>🎬 카메라가 찍은 내 영상</Text>
          <Text style={styles.arrowIcon}>›</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8f9fa',
  },
  header: {
    padding: 24,
    paddingTop: 60,
    backgroundColor: '#fff',
  },
  welcomeText: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#000',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#666',
  },
  mainButtons: {
    padding: 16,
    gap: 16,
  },
  mainButton: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 24,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 3,
  },
  analyzeButton: {
    borderLeftWidth: 4,
    borderLeftColor: '#007AFF',
  },
  shortformButton: {
    borderLeftWidth: 4,
    borderLeftColor: '#FF3B30',
  },
  bestCutButton: {
    borderLeftWidth: 4,
    borderLeftColor: '#FF9500',
  },
  mainButtonIcon: {
    fontSize: 48,
    marginBottom: 12,
  },
  mainButtonTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#000',
    marginBottom: 4,
  },
  mainButtonSubtitle: {
    fontSize: 14,
    color: '#666',
  },
  section: {
    padding: 16,
    marginTop: 8,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#000',
  },
  seeAllButton: {
    fontSize: 14,
    color: '#007AFF',
    fontWeight: '600',
  },
  recordPreviewCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
    marginBottom: 24,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  emptyStateText: {
    fontSize: 15,
    color: '#666',
  },
  arrowIcon: {
    fontSize: 20,
    color: '#ccc',
  },
});
