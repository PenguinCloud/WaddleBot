// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'license_state.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_LicenseState _$LicenseStateFromJson(Map<String, dynamic> json) =>
    _LicenseState(
      status: $enumDecode(_$LicenseStatusEnumMap, json['status']),
      flags: Map<String, bool>.from(json['flags'] as Map),
      lastFetched: json['lastFetched'] == null
          ? null
          : DateTime.parse(json['lastFetched'] as String),
      deviceId: json['deviceId'] as String,
    );

Map<String, dynamic> _$LicenseStateToJson(_LicenseState instance) =>
    <String, dynamic>{
      'status': _$LicenseStatusEnumMap[instance.status]!,
      'flags': instance.flags,
      'lastFetched': instance.lastFetched?.toIso8601String(),
      'deviceId': instance.deviceId,
    };

const _$LicenseStatusEnumMap = {
  LicenseStatus.unknown: 'unknown',
  LicenseStatus.valid: 'valid',
  LicenseStatus.gracePeriod: 'gracePeriod',
  LicenseStatus.invalid: 'invalid',
};
