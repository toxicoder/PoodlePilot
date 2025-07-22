import pyray as rl
from openpilot.common.params import Params
from openpilot.system.ui.lib.widget import Widget, DialogResult
from openpilot.system.ui.lib.application import gui_app # Corrected import
from openpilot.system.ui.lib.list_view import Scroller, button_item, text_item
from openpilot.system.ui.widgets.input_dialog import InputDialog
# Import protobuf messages in case they are needed for type hinting or direct instantiation
from cereal.user_profile_pb2 import ProfileSettings, DrivingModelParameters
from openpilot.system.ui.widgets.confirm_dialog import confirm_dialog, alert_dialog
from openpilot.common.profile_manager import (
    get_profiles_names,
    get_profile_settings,
    save_profile_settings, # Renamed from save_profile to save_profile_settings
    delete_profile,
    load_profile,
    get_current_profile_name,
    create_profile_from_current_settings,
    PROFILE_SUPPORTED_SETTINGS,
    DEFAULT_PROFILE_NAME
)

# Placeholder for a potential future "Edit Profile Settings" screen/layout
# from openpilot.selfdrive.ui.layouts.settings.profile_edit_layout import ProfileEditLayout

class ProfilesLayout(Widget):
    def __init__(self):
        super().__init__()
        self._params = Params()
        self._scroller = Scroller([], line_separator=True, spacing=10)
        self._selected_profile_name: str | None = None
        self._input_dialog: InputDialog | None = None
        # self._edit_profile_dialog: ProfileEditLayout | None = None # For editing settings

        self._load_profile_items()

    def _load_profile_items(self):
        items = []
        profile_names = get_profiles_names()
        current_profile = get_current_profile_name()

        if not profile_names:
            items.append(text_item("No Profiles Yet", "Create a new profile to get started."))

        for name in profile_names:
            is_current = (name == current_profile)
            item_text = f"{name}{' (Current)' if is_current else ''}"
            # We'll use a button_item to make them selectable
            # The actual selection logic will be in _handle_mouse_release or a callback
            items.append(button_item(
                item_text,
                "SELECT" if not is_current else "SELECTED", # Button label changes if current
                description=f"Select to make '{name}' the active profile.",
                callback=lambda n=name: self._on_select_profile(n),
                enabled=not is_current # Disable select for already current profile
            ))

        items.append(button_item(
            "Create New Profile",
            "CREATE",
            description="Create a new profile based on current settings.",
            callback=self._on_create_new_profile
        ))

        # Edit and Delete buttons should only be active if a profile can be selected/exists
        # For simplicity, let's assume we can always try to edit/delete the 'current' one,
        # or better, enable them once a profile is explicitly selected from the list.
        # Here, we'll tie it to the current_profile, but a dedicated _selected_profile_name might be better.

        can_edit_delete = current_profile != DEFAULT_PROFILE_NAME and current_profile in profile_names

        items.append(button_item(
            "Edit Profile Name", # Later: "Edit Profile Settings"
            "EDIT",
            description=f"Edit the name of the current profile ('{current_profile}').",
            callback=self._on_edit_profile_name, # Later: self._on_edit_profile_settings
            enabled=can_edit_delete
        ))
        items.append(button_item(
            "Delete Profile",
            "DELETE",
            description=f"Delete the current profile ('{current_profile}'). Cannot be undone.",
            callback=self._on_delete_profile,
            enabled=can_edit_delete
        ))

        self._scroller.replace_items(items)
        self._selected_profile_name = current_profile # Default selection to current

    def _on_select_profile(self, profile_name: str):
        if load_profile(profile_name):
            # gui_app.set_modal_overlay(lambda: alert_dialog(f"Profile '{profile_name}' loaded!", duration=2.0)) # Needs gui_app
            print(f"Profile '{profile_name}' loaded successfully.")
        else:
            # gui_app.set_modal_overlay(lambda: alert_dialog(f"Error loading '{profile_name}'!", duration=2.0))
            print(f"Error loading profile '{profile_name}'.")
        self._load_profile_items() # Refresh list to show new "Current"
        # Potentially trigger a UI refresh for sidebar if not automatic

    def _on_create_new_profile(self):
        self._input_dialog = InputDialog(
            parent=self, # Needs a parent or to be handled by gui_app
            title="New Profile Name",
            label_text="Enter a name for the new profile:",
            confirm_text="Create"
        )
        # This would typically be: gui_app.set_modal_overlay(self._input_dialog, self._handle_create_profile_name)
        # For now, we'll simulate the callback directly for testing the logic flow.
        # In real scenario, display the dialog and wait for user input.
        print("INFO: InputDialog for new profile name would be shown here.")
        # Simulate getting a name (e.g., "My New Profile")
        # self._handle_create_profile_name(DialogResult.CONFIRM, "My New Profile")


    def _handle_create_profile_name(self, result: DialogResult, new_name: str | None):
        self._input_dialog = None
        if result == DialogResult.CONFIRM and new_name and new_name.strip():
            clean_name = new_name.strip()
            if clean_name == DEFAULT_PROFILE_NAME:
                # gui_app.set_modal_overlay(lambda: alert_dialog(f"Cannot use '{DEFAULT_PROFILE_NAME}' as name.", duration=2.5))
                print(f"Error: Cannot use '{DEFAULT_PROFILE_NAME}' as profile name.")
                return
            if clean_name in get_profiles_names():
                # gui_app.set_modal_overlay(lambda: alert_dialog(f"Profile '{clean_name}' already exists.", duration=2.5))
                print(f"Error: Profile '{clean_name}' already exists.")
                return

            if create_profile_from_current_settings(clean_name):
                # gui_app.set_modal_overlay(lambda: alert_dialog(f"Profile '{clean_name}' created.", duration=2.0))
                print(f"Profile '{clean_name}' created successfully.")
                load_profile(clean_name) # Optionally make the new profile current
            else:
                # gui_app.set_modal_overlay(lambda: alert_dialog(f"Error creating '{clean_name}'.", duration=2.0))
                print(f"Error creating profile '{clean_name}'.")
        self._load_profile_items()

    def _on_edit_profile_name(self):
        current_name = get_current_profile_name()
        if current_name == DEFAULT_PROFILE_NAME:
            # gui_app.set_modal_overlay(lambda: alert_dialog("Cannot rename Default profile.", duration=2.0))
            print("Info: Cannot rename Default profile.")
            return

        self._input_dialog = InputDialog(
            parent=self,
            title="Edit Profile Name",
            label_text=f"Enter new name for '{current_name}':",
            initial_text=current_name,
            confirm_text="Rename"
        )
        # gui_app.set_modal_overlay(self._input_dialog, self._handle_edit_profile_name)
        print(f"INFO: InputDialog for editing profile name '{current_name}' would be shown here.")
        # Simulate: self._handle_edit_profile_name(DialogResult.CONFIRM, "New Name For Profile")

    def _handle_edit_profile_name(self, result: DialogResult, new_name: str | None):
        old_name = get_current_profile_name() # Assuming we are editing the current one
        self._input_dialog = None

        if result == DialogResult.CONFIRM and new_name and new_name.strip():
            clean_new_name = new_name.strip()
            if clean_new_name == old_name:
                return # No change
            if clean_new_name == DEFAULT_PROFILE_NAME:
                # gui_app.set_modal_overlay(lambda: alert_dialog(f"Cannot use '{DEFAULT_PROFILE_NAME}' as name.", duration=2.5))
                print(f"Error: Cannot use '{DEFAULT_PROFILE_NAME}' for rename.")
                return
            if clean_new_name in get_profiles_names():
                # gui_app.set_modal_overlay(lambda: alert_dialog(f"Profile '{clean_new_name}' already exists.", duration=2.5))
                print(f"Error: Profile name '{clean_new_name}' already exists.")
                return

            settings = get_profile_settings(old_name)
            if settings is not None:
                if save_profile_settings(clean_new_name, settings): # Save under new name
                    delete_profile(old_name) # Delete old name
                    load_profile(clean_new_name) # Make new name current
                    # gui_app.set_modal_overlay(lambda: alert_dialog(f"Profile renamed to '{clean_new_name}'.", duration=2.0))
                    print(f"Profile renamed from '{old_name}' to '{clean_new_name}'.")
                else:
                    # gui_app.set_modal_overlay(lambda: alert_dialog("Error renaming profile.", duration=2.0))
                    print("Error renaming profile.")
            else:
                # gui_app.set_modal_overlay(lambda: alert_dialog(f"Could not find settings for '{old_name}'.", duration=2.0))
                print(f"Error: Could not find settings for '{old_name}' during rename.")
        self._load_profile_items()

    # def _on_edit_profile_settings(self):
    #     current_name = get_current_profile_name()
    #     if current_name == DEFAULT_PROFILE_NAME:
    #         gui_app.set_modal_overlay(lambda: alert_dialog("Settings for Default profile are fixed.", duration=2.5))
    #         return
    #     if not self._edit_profile_dialog:
    #         self._edit_profile_dialog = ProfileEditLayout(current_name) # Needs this class
    #     gui_app.set_modal_overlay(self._edit_profile_dialog, self._handle_edit_profile_settings)

    # def _handle_edit_profile_settings(self, result: DialogResult):
    #     self._edit_profile_dialog = None
    #     if result == DialogResult.SAVE: # Assuming ProfileEditLayout has a way to signal save
    #         gui_app.set_modal_overlay(lambda: alert_dialog("Profile settings saved.", duration=2.0))
    #     self._load_profile_items() # Refresh, though not strictly necessary if only settings changed


    def _on_delete_profile(self):
        profile_to_delete = get_current_profile_name() # Or self._selected_profile_name
        if profile_to_delete == DEFAULT_PROFILE_NAME:
            # gui_app.set_modal_overlay(lambda: alert_dialog("Cannot delete Default profile.", duration=2.0))
            print("Info: Cannot delete Default profile.")
            return

        # confirm_dialog_widget = confirm_dialog(
        #     f"Delete Profile: {profile_to_delete}?",
        #     "This cannot be undone.",
        #     confirm_text="Delete"
        # )
        # gui_app.set_modal_overlay(confirm_dialog_widget, lambda res: self._handle_delete_profile_confirm(res, profile_to_delete))
        print(f"INFO: Confirmation dialog for deleting '{profile_to_delete}' would be shown here.")
        # Simulate: self._handle_delete_profile_confirm(DialogResult.CONFIRM, profile_to_delete)


    def _handle_delete_profile_confirm(self, result: DialogResult, profile_name: str):
        if result == DialogResult.CONFIRM:
            if delete_profile(profile_name):
                # gui_app.set_modal_overlay(lambda: alert_dialog(f"Profile '{profile_name}' deleted.", duration=2.0))
                print(f"Profile '{profile_name}' deleted.")
                # If current profile was deleted, profile_manager's ensure_default_profile
                # (if called on next load or by load_profile) should handle fallback.
                # For immediate effect, we can explicitly load Default.
                if get_current_profile_name() == profile_name: # It was the current one
                    load_profile(DEFAULT_PROFILE_NAME)
            else:
                # gui_app.set_modal_overlay(lambda: alert_dialog(f"Error deleting '{profile_name}'.", duration=2.0))
                print(f"Error deleting '{profile_name}'.")
        self._load_profile_items()

    def _render(self, rect: rl.Rectangle):
        self._scroller.render(rect)

    def _handle_mouse_release(self, mouse_pos: rl.Vector2) -> bool:
        # Scroller handles its own clicks for items with callbacks
        return super()._handle_mouse_release(mouse_pos)

    def refresh(self):
        """Called when the panel becomes visible."""
        self._load_profile_items()

# Placeholder for the actual gui_app if we were running this standalone
# class MockGuiApp:
#     def set_modal_overlay(self, dialog_factory, callback=None):
#         print(f"MockGuiApp: Setting modal overlay. Type: {type(dialog_factory()) if callable(dialog_factory) else type(dialog_factory)}")
#         # Simulate interaction if needed for testing flow
#         if isinstance(dialog_factory, InputDialog) or (callable(dialog_factory) and isinstance(dialog_factory(), InputDialog)):
#             print("Simulating InputDialog CONFIRM with 'TestName'")
#             if callback:
#                 callback(DialogResult.CONFIRM, "TestName")
#         elif callable(dialog_factory): # For confirm/alert
#             # Simulate confirm dialog
#             print("Simulating ConfirmDialog CONFIRM")
#             if callback:
#                  callback(DialogResult.CONFIRM)


# gui_app = MockGuiApp() # Replace with actual gui_app when integrated

if __name__ == "__main__":
    # This is for basic testing of the layout logic standalone
    # You'd need to mock pyray, gui_app, and other dependencies or run within OP UI environment.
    print("ProfilesLayout module loaded. Basic structure defined.")
    print("PROFILE_SUPPORTED_SETTINGS:", PROFILE_SUPPORTED_SETTINGS)

    # Initialize params for standalone testing if needed
    # params = Params()
    # if not params.get("CurrentProfileName"):
    #     params.put("CurrentProfileName", DEFAULT_PROFILE_NAME)

    # Test layout logic (conceptual)
    # layout = ProfilesLayout()
    # layout._load_profile_items() # Populate items
    # print(f"Scroller items: {len(layout._scroller._items)}")

    # Simulate creating a profile
    # layout._on_create_new_profile() # This would show a dialog
    # layout._handle_create_profile_name(DialogResult.CONFIRM, "My Test Profile")
    # print(f"Scroller items after create: {len(layout._scroller._items)}")
    # print("Profiles:", get_profiles_names())

    # Simulate selecting a profile
    # if "My Test Profile" in get_profiles_names():
    #     layout._on_select_profile("My Test Profile")
    #     print("Current profile after select:", get_current_profile_name())

    # Simulate renaming
    # if get_current_profile_name() == "My Test Profile":
    #    layout._on_edit_profile_name()
    #    layout._handle_edit_profile_name(DialogResult.CONFIRM, "My Renamed Profile")
    #    print("Profiles after rename:", get_profiles_names())
    #    print("Current profile after rename:", get_current_profile_name())

    # Simulate deleting
    # if "My Renamed Profile" in get_profiles_names():
    #    layout._on_delete_profile() # This needs the current profile to be the one to delete
    #    layout._handle_delete_profile_confirm(DialogResult.CONFIRM, "My Renamed Profile")
    #    print("Profiles after delete:", get_profiles_names())
    #    print("Current profile after delete:", get_current_profile_name())

    # Cleanup test profiles if any were created by profile_manager's test code
    # for name in ["Test Profile 1", "Custom Sport", "My Test Profile", "My Renamed Profile"]:
    #    if name in get_profiles_names():
    #        delete_profile(name)
    # print("Cleaned up test profiles. Final profiles:", get_profiles_names())
    # if get_current_profile_name() not in get_profiles_names():
    #    load_profile(DEFAULT_PROFILE_NAME) # Reset to default
    # print("Final current profile:", get_current_profile_name())
    pass
