import * as ImagePicker from 'expo-image-picker';
import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Alert, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import {
  apiUploadVideo,
  apiCreateAnalysisJob,
  apiGetAnalysisJob,
  pollUntilDone,
} from '@/constants/api';

export default function AnalyzeVideoScreen() {
  const [isLoading, setIsLoading] = useState(false);
  const [loadingText, setLoadingText] = useState('');

  const handleCamera = async () => {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('권한 필요', '카메라 접근 권한이 필요합니다.');
      return;
    }

    // launchCameraAsync: 카메라를 직접 열어 영상 촬영
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: 'videos',          // 올바른 v17 타입 (복수형)
      cameraType: ImagePicker.CameraType.back,  // 후면 카메라
      videoMaxDuration: 120,         // 최대 2분
      videoQuality: ImagePicker.UIImagePickerControllerQualityType.High,
    });

    if (!result.canceled) {
      const asset = result.assets[0];
      await startAnalysis(asset.uri, asset.mimeType ?? undefined, asset.fileName ?? undefined);
    }
  };

  const handleGallery = async () => {
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        Alert.alert('권한 필요', '갤러리 접근 권한이 필요합니다.');
        return;
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: 'videos',
        allowsEditing: false,
      });

      // 디버그: 갤러리 결과 확인 (문제 해결 후 제거)
      if (result.canceled) {
        return; // 사용자가 취소함
      }

      if (!result.assets || result.assets.length === 0) {
        Alert.alert('오류', '선택된 영상이 없습니다.');
        return;
      }

      const asset = result.assets[0];
      if (!asset.uri) {
        Alert.alert('오류', '영상 URI를 가져올 수 없습니다.');
        return;
      }

      await startAnalysis(asset.uri, asset.mimeType ?? undefined, asset.fileName ?? undefined);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      Alert.alert('갤러리 오류', msg);
    }
  };

  const startAnalysis = async (videoUri: string, mimeType?: string, fileName?: string) => {
    setIsLoading(true);
    try {
      // 1단계: 영상 업로드
      setLoadingText('영상 업로드 중...');
      const uploadResult = await apiUploadVideo(videoUri, mimeType, fileName);

      // 2단계: 분석 작업 생성
      setLoadingText('AI 분석 중...');
      const job = await apiCreateAnalysisJob(uploadResult.video_id);

      // 3단계: 완료까지 폴링
      setLoadingText('분석 결과 대기 중...');
      const doneJob = await pollUntilDone(() => apiGetAnalysisJob(job.id));

      // 4단계: 결과 화면으로 이동
      router.push({
        pathname: '/analysis-result',
        params: { jobId: String(doneJob.id) },
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      Alert.alert('분석 오류', `${msg}\n\nURI: ${videoUri?.substring(0, 50)}...`);
    } finally {
      setIsLoading(false);
      setLoadingText('');
    }
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#007AFF" />
        <Text style={styles.loadingTitle}>AI가 분석 중이에요</Text>
        <Text style={styles.loadingSubtitle}>
          {loadingText || '잠시만 기다려주세요 😊'}
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.canGoBack() ? router.back() : router.replace('/(tabs)')}>
          <Text style={styles.backButton}>← 뒤로</Text>
        </TouchableOpacity>
        <Text style={styles.title}>영상 분석하기</Text>
      </View>

      <View style={styles.content}>
        <Text style={styles.subtitle}>러닝 영상을 업로드해주세요</Text>
        <Text style={styles.description}>
          AI가 자세를 분석하고{'\n'}개선 방안을 알려드려요
        </Text>

        <View style={styles.buttonContainer}>
          <TouchableOpacity style={styles.uploadButton} onPress={handleCamera}>
            <Text style={styles.buttonIcon}>📷</Text>
            <Text style={styles.buttonTitle}>카메라로 촬영하기</Text>
            <Text style={styles.buttonSubtitle}>지금 바로 촬영하세요</Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.uploadButton} onPress={handleGallery}>
            <Text style={styles.buttonIcon}>🖼️</Text>
            <Text style={styles.buttonTitle}>갤러리에서 선택</Text>
            <Text style={styles.buttonSubtitle}>저장된 영상을 선택하세요</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.tips}>
          <Text style={styles.tipsTitle}>💡 촬영 팁</Text>
          <Text style={styles.tipsText}>• 전신이 다 나오도록 촬영해주세요</Text>
          <Text style={styles.tipsText}>• 밝은 곳에서 촬영하면 더 정확해요</Text>
          <Text style={styles.tipsText}>• 10초 이상 촬영을 권장합니다</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff' },
  header: {
    paddingTop: 60, paddingHorizontal: 20, paddingBottom: 20,
    borderBottomWidth: 1, borderBottomColor: '#f0f0f0',
  },
  backButton: { fontSize: 16, color: '#007AFF', marginBottom: 16 },
  title: { fontSize: 28, fontWeight: 'bold', color: '#000' },
  content: { flex: 1, padding: 20 },
  subtitle: { fontSize: 20, fontWeight: '600', color: '#000', marginBottom: 8 },
  description: { fontSize: 16, color: '#666', marginBottom: 32, lineHeight: 24 },
  buttonContainer: { gap: 16, marginBottom: 32 },
  uploadButton: {
    backgroundColor: '#f8f9fa', borderRadius: 16, padding: 24,
    alignItems: 'center', borderWidth: 2, borderColor: '#e9ecef',
  },
  buttonIcon: { fontSize: 48, marginBottom: 12 },
  buttonTitle: { fontSize: 18, fontWeight: 'bold', color: '#000', marginBottom: 4 },
  buttonSubtitle: { fontSize: 14, color: '#666' },
  tips: { backgroundColor: '#f8f9fa', borderRadius: 12, padding: 20 },
  tipsTitle: { fontSize: 16, fontWeight: 'bold', color: '#000', marginBottom: 12 },
  tipsText: { fontSize: 14, color: '#666', marginBottom: 6, lineHeight: 20 },
  loadingContainer: {
    flex: 1, backgroundColor: '#fff',
    alignItems: 'center', justifyContent: 'center', padding: 40,
  },
  loadingTitle: {
    fontSize: 22, fontWeight: 'bold', color: '#000',
    marginTop: 24, marginBottom: 12,
  },
  loadingSubtitle: { fontSize: 16, color: '#666', textAlign: 'center', lineHeight: 24 },
});
