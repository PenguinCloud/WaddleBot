// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'gazer_settings.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_GazerSettings _$GazerSettingsFromJson(
  Map<String, dynamic> json,
) => _GazerSettings(
  target: StreamTargetSettings.fromJson(json['target'] as Map<String, dynamic>),
  quality: QualitySettings.fromJson(json['quality'] as Map<String, dynamic>),
  audio: $enumDecode(_$AudioSourceChoiceEnumMap, json['audio']),
  forceLibuvc: json['forceLibuvc'] as bool,
);

Map<String, dynamic> _$GazerSettingsToJson(_GazerSettings instance) =>
    <String, dynamic>{
      'target': instance.target.toJson(),
      'quality': instance.quality.toJson(),
      'audio': _$AudioSourceChoiceEnumMap[instance.audio]!,
      'forceLibuvc': instance.forceLibuvc,
    };

const _$AudioSourceChoiceEnumMap = {
  AudioSourceChoice.auto: 'auto',
  AudioSourceChoice.mic: 'mic',
  AudioSourceChoice.usbAudio: 'usbAudio',
  AudioSourceChoice.silence: 'silence',
};
