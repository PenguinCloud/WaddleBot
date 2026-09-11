import 'package:flutter/material.dart';

/// Displays a secret value masked except for its last 4 characters, with
/// a tap-to-reveal toggle showing the full value.
///
/// Used for read-only secret display (e.g. the status panel's connection
/// details) where the value is shown, not edited — editable secret inputs
/// (Settings screen's stream key/password fields) use a plain obscured
/// `TextFormField` with its own reveal toggle instead, since this widget
/// renders static text rather than an editable field.
class MaskedText extends StatefulWidget {
  const MaskedText({
    super.key,
    required this.value,
    required this.revealSemanticsLabel,
    this.maskChar = '•',
  });

  /// The secret value to display, masked by default.
  final String value;

  /// Accessibility label for the reveal/hide toggle button.
  final String revealSemanticsLabel;

  /// Character used to mask every hidden position of [value].
  final String maskChar;

  @override
  State<MaskedText> createState() => _MaskedTextState();
}

class _MaskedTextState extends State<MaskedText> {
  bool _revealed = false;

  String get _masked {
    final String v = widget.value;
    if (v.isEmpty) return '';
    if (v.length <= 4) return widget.maskChar * v.length;
    return widget.maskChar * (v.length - 4) + v.substring(v.length - 4);
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(_revealed ? widget.value : _masked),
        Semantics(
          label: widget.revealSemanticsLabel,
          button: true,
          child: IconButton(
            icon: Icon(_revealed ? Icons.visibility_off : Icons.visibility),
            onPressed: () => setState(() => _revealed = !_revealed),
          ),
        ),
      ],
    );
  }
}
