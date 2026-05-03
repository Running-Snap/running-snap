import { useLocalSearchParams, router } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator, Alert, Dimensions, Image, Modal,
  ScrollView, StyleSheet, Text, TouchableOpacity, View,
} from 'react-native';
import { apiGetBestcutJob, API_BASE } from '@/constants/api';

type BestCut = {
  photo_url: string | null;
  timestamp: string;
  description: string;
};
const getCutUri = (cut: BestCut) => {
  if (!cut.photo_url) return null;

  return cut.photo_url.startsWith('http')
    ? cut.photo_url
    : `${API_BASE}${cut.photo_url}`;
};

export default function BestCutResultScreen() {
  const { jobId } = useLocalSearchParams<{ jobId: string }>();
  const [cuts, setCuts] = useState<BestCut[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [viewingCut, setViewingCut] = useState<BestCut | null>(null);

  useEffect(() => {
  if (!jobId) return;
  apiGetBestcutJob(Number(jobId))
    .then(job => {
      if (job.result_json) {
        const parsed = JSON.parse(job.result_json);
        // ✅ { bestcut: [...], poster: [...] } 구조 대응
        const cutsArray = Array.isArray(parsed)
          ? parsed
          : parsed.bestcut ?? [];
        setCuts(cutsArray);
      }
    })
    .catch(() => {})
    .finally(() => setIsLoading(false));
}, [jobId]);

 const handleSaveCut = (cut: BestCut) => {
  const uri = getCutUri(cut);

  if (uri) {
    Alert.alert('저장', `${cut.timestamp} 컷 저장 링크:\n${uri}`);
  } else {
    Alert.alert('알림', '사진 파일이 없습니다.');
  }
};


  const handleSaveAll = () => {
    Alert.alert('저장 완료', `${cuts.length}개의 베스트 컷 정보를 확인하세요.`);
  };

  if (isLoading) {

    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#FF9500" />
        <Text style={styles.loadingText}>결과 불러오는 중...</Text>
      </View>
    );
  }
const viewingUri = viewingCut ? getCutUri(viewingCut) : null;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.canGoBack() ? router.back() : router.replace('/(tabs)')}>
          <Text style={styles.backButton}>← 뒤로</Text>
        </TouchableOpacity>
        <Text style={styles.title}>베스트 컷 결과</Text>
        <Text style={styles.subtitle}>총 {cuts.length}개의 베스트 컷</Text>
      </View>

      <ScrollView style={styles.content}>
        <View style={styles.summaryCard}>
          <Text style={styles.summaryIcon}>🏆</Text>
          <Text style={styles.summaryTitle}>베스트 컷 추출 완료!</Text>
          <Text style={styles.summaryText}>
            AI가 영상에서 {cuts.length}개의{'\n'}최고의 순간을 찾아냈어요
          </Text>
        </View>

        {cuts.map((cut, index) => {
            const uri = getCutUri(cut);
            return (
          <View key={index} style={styles.cutCard}>
            <TouchableOpacity onPress={() => uri && setViewingCut(cut)}>
              {uri ? (
          <Image
            source={{ uri }}
            style={styles.cutImage}
            resizeMode="cover"
          />
              ) : (
                <View style={styles.cutImagePlaceholder}>
                  <Text style={styles.cutImageIcon}>📸</Text>
                  <Text style={styles.cutTimestamp}>{cut.timestamp}</Text>
                </View>
              )}
            </TouchableOpacity>
            <View style={styles.cutInfo}>
              <Text style={styles.cutNumber}>베스트 컷 {index + 1}</Text>
              <Text style={styles.cutDescription}>{cut.description}</Text>
              <Text style={styles.cutTime}>📍 영상 {cut.timestamp} 지점</Text>
            </View>
            <TouchableOpacity style={styles.saveButton} onPress={() => handleSaveCut(cut)}>
              <Text style={styles.saveButtonText}>저장</Text>
            </TouchableOpacity>
          </View>
            );
})}
      </ScrollView>

      {/* 전체화면 이미지 모달 */}
      <Modal
        visible={!!viewingCut}
        transparent
        animationType="fade"
        onRequestClose={() => setViewingCut(null)}
      >
        <View style={styles.modalOverlay}>
          <TouchableOpacity style={styles.modalClose} onPress={() => setViewingCut(null)}>
            <Text style={styles.modalCloseText}>✕</Text>
          </TouchableOpacity>
          {viewingUri && (
  <Image
    source={{ uri: viewingUri }}
    style={styles.modalImage}
    resizeMode="contain"
  />
)}
          <View style={styles.modalInfo}>
            <Text style={styles.modalDescription}>{viewingCut?.description}</Text>
            <Text style={styles.modalTimestamp}>📍 {viewingCut?.timestamp}</Text>
          </View>
        </View>
      </Modal>

      <View style={styles.footer}>
        <TouchableOpacity style={styles.saveAllButton} onPress={handleSaveAll}>
          <Text style={styles.saveAllButtonText}>전체 저장 ({cuts.length}개)</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.homeButton} onPress={() => router.replace('/(tabs)')}>
          <Text style={styles.homeButtonText}>홈으로 돌아가기</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8f9fa' },
  loadingContainer: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  loadingText: { fontSize: 16, color: '#666', marginTop: 12 },
  header: {
    paddingTop: 60, paddingHorizontal: 20, paddingBottom: 20,
    backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#f0f0f0',
  },
  backButton: { fontSize: 16, color: '#007AFF', marginBottom: 16 },
  title: { fontSize: 28, fontWeight: 'bold', color: '#000', marginBottom: 4 },
  subtitle: { fontSize: 14, color: '#666' },
  content: { flex: 1, padding: 16 },
  summaryCard: {
    backgroundColor: '#fff', borderRadius: 16, padding: 24,
    alignItems: 'center', marginBottom: 20, borderWidth: 2, borderColor: '#FF9500',
  },
  summaryIcon: { fontSize: 48, marginBottom: 12 },
  summaryTitle: { fontSize: 20, fontWeight: 'bold', color: '#000', marginBottom: 8 },
  summaryText: { fontSize: 14, color: '#666', textAlign: 'center', lineHeight: 22 },
  cutCard: {
    backgroundColor: '#fff', borderRadius: 12, padding: 12, marginBottom: 12,
    flexDirection: 'row', alignItems: 'center',
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2,
  },
  cutImage: { width: 70, height: 70, borderRadius: 8, marginRight: 12 },
  cutImagePlaceholder: {
    width: 70, height: 70, backgroundColor: '#f0f0f0', borderRadius: 8,
    alignItems: 'center', justifyContent: 'center', marginRight: 12,
  },
  cutImageIcon: { fontSize: 24 },
  cutTimestamp: { fontSize: 11, color: '#999', marginTop: 4 },
  cutInfo: { flex: 1 },
  cutNumber: { fontSize: 15, fontWeight: 'bold', color: '#000', marginBottom: 4 },
  cutDescription: { fontSize: 13, color: '#FF9500', fontWeight: '600', marginBottom: 4 },
  cutTime: { fontSize: 12, color: '#999' },
  saveButton: { backgroundColor: '#FF9500', borderRadius: 8, paddingVertical: 8, paddingHorizontal: 14 },
  saveButtonText: { color: '#fff', fontSize: 13, fontWeight: 'bold' },
  footer: { padding: 16, backgroundColor: '#fff', borderTopWidth: 1, borderTopColor: '#f0f0f0', gap: 10 },
  saveAllButton: { backgroundColor: '#FF9500', borderRadius: 12, padding: 16, alignItems: 'center' },
  saveAllButtonText: { color: '#fff', fontSize: 16, fontWeight: 'bold' },
  homeButton: {
    backgroundColor: '#fff', borderRadius: 12, padding: 16,
    alignItems: 'center', borderWidth: 1, borderColor: '#ddd',
  },
  homeButtonText: { color: '#666', fontSize: 16, fontWeight: '600' },
  modalOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.95)',
    justifyContent: 'center', alignItems: 'center',
  },
  modalClose: {
    position: 'absolute', top: 60, right: 20, zIndex: 10,
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.2)',
    alignItems: 'center', justifyContent: 'center',
  },
  modalCloseText: { color: '#fff', fontSize: 20, fontWeight: 'bold' },
  modalImage: {
    width: Dimensions.get('window').width - 32,
    height: Dimensions.get('window').height * 0.6,
  },
  modalInfo: {
    paddingHorizontal: 24, paddingTop: 20, alignItems: 'center',
  },
  modalDescription: {
    color: '#fff', fontSize: 16, fontWeight: '600',
    textAlign: 'center', marginBottom: 8,
  },
  modalTimestamp: { color: 'rgba(255,255,255,0.7)', fontSize: 14 },
});
