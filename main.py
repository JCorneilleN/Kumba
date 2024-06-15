
from kivy.uix.screenmanager import ScreenManager
from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.network.urlrequest import UrlRequest
from urllib.parse import quote
from kivy.logger import Logger
from kivymd.uix.textfield import MDTextField
from kivy.metrics import dp
from kivy.uix.dropdown import DropDown
from kivy.clock import Clock
from pathlib import Path
from datetime import datetime
from kivymd.uix.pickers import MDDatePicker, MDTimePicker
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.button import  MDIconButton
from kivymd.uix.button import MDRaisedButton
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.card import MDCard
from kivymd.toast import toast
from firebase_admin import credentials, firestore, auth
from google.cloud import firestore
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


import csv

import threading
import firebase_admin
import re 
import requests
import os




# Access environment variables
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
GOOGLE_APPLICATION_CREDENTIALS_PATH = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
FIREBASE_CREDENTIALS_PATH = os.getenv('FIREBASE_CREDENTIALS')
FIREBASE_STORAGE_BUCKET = os.getenv('FIREBASE_STORAGE_BUCKET')
FIREBASE_API_KEY = os.getenv('FIREBASE_API_KEY')
os.environ['KIVY_NO_MTDEV'] = '1'
# Firebase setup
cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
firebase_admin.initialize_app(cred, {
    'storageBucket': FIREBASE_STORAGE_BUCKET
})

db = firestore.Client()


Window.size = (350, 610)
#Window.borderless = True

# Load colleges and universities from CSV file
colleges = []
data_folder = Path(__file__).parent / 'data'
colleges_file = data_folder / 'colleges.csv'
with open(colleges_file, 'r') as file:
    reader = csv.reader(file)
    next(reader)  # Skip the header row
    for row in reader:
        colleges.append(row[3])  # Assuming the college name is in the 4th column (index 3)

# Address
def filter_address(address):
    # Remove "United States" from the address
    return address.replace("United States", "").strip(", ")

def fetch_address_suggestions(query, on_success):
    query_encoded = quote(query)
    url = f"https://nominatim.openstreetmap.org/search?q={query_encoded}&format=json"
    headers = {'User-Agent': 'kumba'}
    def filtered_on_success(req, result):
        # Filter "United States" from all results
        filtered_result = [{**item, "display_name": filter_address(item['display_name'])} for item in result]
        on_success(req, filtered_result)
    
    UrlRequest(url, on_success=filtered_on_success, req_headers=headers)


class MDAutocompleteTextField(MDTextField):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dropdown = DropDown()
        self.bind(on_text=self.on_text)

    def on_text(self, instance, value):
        # Throttle the suggestions to avoid spamming
        Clock.unschedule(self.display_suggestions)
        Clock.schedule_once(self.display_suggestions, 0.5)

    def display_suggestions(self, dt):
        # Dismiss and clear the dropdown if it's already open
        if self.dropdown.parent:
            self.dropdown.dismiss()
        self.dropdown.clear_widgets()

        def on_success(req, result):
            if result:
                for item in result:
                    btn = Button(text=item['display_name'], size_hint_y=None, height=44)
                    # Use a more direct method for handling the button press
                    btn.bind(on_release=self.select_and_dismiss)
                    self.dropdown.add_widget(btn)
                if not self.dropdown.parent:
                    self.dropdown.open(self)
            else:
                Logger.warning('No suggestions found.')

        # Dummy function for demonstration; replace with actual function to fetch data
        fetch_address_suggestions(self.text, on_success)

    def select_and_dismiss(self, btn):
        """Set text from button, dismiss dropdown, and unfocus text field."""
        self.text = btn.text  # Set the text to the button's text
        self.dropdown.dismiss()  # Dismiss the dropdown
        self.focus = False  # Optionally remove focus from the text field

# School Input
class SchoolInput(TextInput):
    dropdown = None
    filter_trigger = None

    def __init__(self, **kwargs):
        super(SchoolInput, self).__init__(**kwargs)
        self.bind(text=self.on_text)
        self.dropdown = DropDown()
        self.filter_trigger = Clock.create_trigger(self.filter_colleges, 0.5)

    def on_text(self, instance, value):
        self.text = ''.join([s for s in value.title() if s.isalnum() or s == ' '])
        self.filter_trigger()

    def filter_colleges(self, *args):
        value = self.text
        threading.Thread(target=self.update_dropdown, args=(value,)).start()

    def update_dropdown(self, value):
        try:
            matched_colleges = [college for college in colleges if value.lower() in college.lower()][:50]  # Limit results
            Clock.schedule_once(lambda dt: self.populate_dropdown(matched_colleges))
        except Exception as e:
            print(f'Error updating dropdown: {e}')

    def populate_dropdown(self, matched_colleges):
        self.dropdown.clear_widgets()
        for college in matched_colleges:
            btn = Button(text=college, size_hint_y=None, height=44)
            btn.bind(on_release=lambda btn: self.select_and_dismiss(btn.text))
            self.dropdown.add_widget(btn)

        if matched_colleges and not self.dropdown.attach_to:
            self.dropdown.open(self)

    def select_and_dismiss(self, text):
        self.text = text
        self.dropdown.dismiss()

    def on_touch_up(self, touch):
        if self.dropdown.parent:
            self.dropdown.dismiss()
        return super(SchoolInput, self).on_touch_up(touch)


# SLope 
class Slope(MDApp):
    email = StringProperty('No email')
    first_name = StringProperty('No Name')
    last_name = StringProperty('No Last Name')
    dob = StringProperty('No DOB')
    school_input=StringProperty('No School')
    dialog = None
    current_user = {}
    current_user_id = StringProperty(None)
    verification_code = None  # Temporary storage for the verification code
    current_user_id = StringProperty(None, allownone=True)
    current_user_name = "Unknown"
    current_receiver_name = StringProperty("Unknown")
    current_receiver_id = StringProperty(None)
  
    def build(self):
        self.theme_cls.material_style = "M3"
       
        self.screen_manager = ScreenManager()
        # Load and add screens
        self.screen_manager.add_widget(Builder.load_file("main.kv"))
        self.screen_manager.add_widget(Builder.load_file("login.kv"))
        self.screen_manager.add_widget(Builder.load_file("signup.kv"))
        self.screen_manager.add_widget(Builder.load_file("reset_password.kv"))
        self.screen_manager.add_widget(Builder.load_file("welcome.kv"))
        self.screen_manager.add_widget(Builder.load_file("home.kv"))
        self.screen_manager.add_widget(Builder.load_file("page.kv"))
        self.screen_manager.add_widget(Builder.load_file("verify.kv"))
        self.screen_manager.add_widget(Builder.load_file("driver.kv"))

        
    
        # Load rides on startup
        self.load_rides()
        #deleting past rides
        self.start_deletion_schedule()
        self.delete_past_rides()
        

         # Schedule loading of chats after the startup sequenc
    
        return self.screen_manager


    
    def __init__(self, **kwargs): 
        super(Slope, self).__init__(**kwargs)

    
        

    #Date picker for date of birth
    def show_date_picker_dob(self, target):
        date_dialog = MDDatePicker()
        # Fix the lambda to match the expected parameters
        date_dialog.bind(on_save=lambda instance, value, date_range: self.on_save_dob(instance, value, target))
        date_dialog.open()

    #Date picker for travel
    def show_date_picker_travel(self, target):
        """Show date picker with a minimum date set to today for travel scheduling."""
        today = datetime.now().date()
        date_dialog = MDDatePicker(min_date=today)
        date_dialog.bind(on_save=lambda instance, value, date_range: self.handle_travel_date(instance, value, target))
        date_dialog.open()

    def handle_travel_date(self, instance, value, target):
        """Handles the travel date selected from the date picker."""
        selected_date = value
        if selected_date < datetime.now().date():
            toast("Travel date cannot be in the past.")
        else:
            formatted_date = selected_date.strftime('%m-%d-%Y')
            target.text = formatted_date  # Update the text field with the selected date
            toast(f"Travel date set to: {formatted_date}")

    def switch_to_page(self):
        # Switch to the page screen
        self.root.current = 'page'
    
    def show_time_picker(self, target):
        '''Open time picker dialog and pass the target where the time will be displayed.'''
        time_dialog = MDTimePicker()
        time_dialog.bind(time=lambda instance, time: self.on_time_select(instance, time, target))
        time_dialog.open()

    def on_time_select(self, instance, time, target):
        '''Event for time selection, updating the target TextInput with the selected time.'''
        target.text = time.strftime('%H:%M')
    
    #Save for date of birth
    def on_save_dob(self, picker_instance, selected_date, target):
        '''Updates the target text field with the selected date.'''
        formatted_date = selected_date.strftime('%m-%d-%Y')
        target.text = formatted_date  # Update the target TextInput
        target.focus = False
        today = datetime.now().date()
        age = today.year - selected_date.year - ((today.month, today.day) < (selected_date.month, selected_date.day))
        if age < 18:
            target.text = ""
            self.show_dialog("You must be at least 18 years old to register.")
    



    def validate_email(self, email):
        return re.match(r".*@.*\.edu$", email) is not None

    def validate_password(self, password, confirm_password):
        return password == confirm_password
    
    #sign up

    def on_signup(self):
        current_screen = self.screen_manager.get_screen('signup')
        email = current_screen.ids.email_input.text.strip()
        password = current_screen.ids.password_input.text.strip()
        first_name = current_screen.ids.first_name_input.text.strip()
        last_name = current_screen.ids.last_name_input.text.strip()
        gender = current_screen.ids.gender_input.text.strip()
        school = current_screen.ids.school_input.text.strip()
        dob = current_screen.ids.dob.text.strip()
    
        # Check if all fields are filled
        if not (email and password and first_name and last_name and gender and school and dob):
            current_screen.ids.signup_message_label.text = "All fields are required."
            return
         
        if not email:
            current_screen.ids.signup_message_label.text = "Email is missing"
            return
        if not first_name:
            current_screen.ids.signup_message_label.text = "First name is missing"
            return
        if not last_name:
            current_screen.ids.signup_message_label.text = "Last name is missing"
            return
        if not school:
            current_screen.ids.signup_message_label.text = "School is missng"
            return
        if not dob:
            current_screen.ids.signup_message_label.text = "Date of Birth is missing"
            return
    
        # Additional checks for email and password
        if not self.validate_email(email):
            current_screen.ids.signup_message_label.text = "Please use a valid email address."
            return
    
        if not self.validate_password(password, current_screen.ids.password_confirm_input.text.strip()):
            current_screen.ids.signup_message_label.text = "Passwords do not match."
            return

    # Proceed with Firebase signup if all validations pass
    # Your existing Firebase signup code here...

    
        verification_code = self.generate_verification_code()
    
        try:
            # Create the user in Firebase Authentication
            user_record = auth.create_user(email=email, password=password)
            
            # Assign the user ID to the app's current_user_id
            self.current_user_id = user_record.uid
    
            # Store user details in Firestore
            db.collection('users').document(user_record.uid).set({
                "first_name": current_screen.ids.first_name_input.text.strip(),
                "last_name": current_screen.ids.last_name_input.text.strip(),
                "gender": current_screen.ids.gender_input.text.strip(),
                "school": current_screen.ids.school_input.text.strip(),
                "dob": current_screen.ids.dob.text.strip(),
                "email": email,
                "verification_code": verification_code  # Store verification code
            })
    
            # Send a verification email with the generated verification code
            self.send_verification_email(email, verification_code)
    
            # Notify the user and navigate to the verification screen
            self.show_dialog("A verification code has been sent to your email. Please enter it to complete registration.", "Sign Up Successful")
            self.screen_manager.current = "verify"
    
        except Exception as e:
            # Show any error messages
            self.show_dialog(str(e))


    def generate_verification_code(self):
        """Generate a random 6-digit verification code."""
        import random
        self.verification_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        return self.verification_code

    def send_verification_email(self, email, code):
        code = self.generate_verification_code()
        message = Mail(
            from_email='corneillengoy@gmail.com',
            to_emails=email,
            subject='Your Verification Code',
            html_content=f'Your verification code is: <strong>{code}</strong>. Please enter this code in the app to complete your registration.'
        )
        try:
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            response = sg.send(message)
            print(f"Email sent: {response.status_code}")
        except Exception as e:
            print(f"Error sending email with SendGrid: {str(e)}")

    def verify_code(self, code_input):
        if code_input == self.verification_code:
            # Code is correct
            self.show_dialog("Email verified successfully! Now go Log in", "Verification")
            self.screen_manager.current = "login"
            self.verification_code = None  # Clear the code after successful verification
        else:
            self.show_dialog("Incorrect verification code.", "Verification Failed")


    #Login

    def login_user(self):
        login_screen = self.screen_manager.get_screen('login')
        email = login_screen.ids.email_input.text.strip()
        password = login_screen.ids.password_input.text.strip()
    
        # Check for missing fields
        if not email or not password:
            self.show_dialog("Please enter both email and password", "Login Failed")
            return
    
        # Validate email
        if not self.validate_email(email):
            self.show_dialog("Invalid email format", "Login Failed")
            return
    
        # Firebase REST API URL for sign-in
        api_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
        data = {
            'email': email,
            'password': password,
            'returnSecureToken': True
        }
        response = requests.post(api_url, json=data)
        result = response.json()
    
        if response.ok:
            try:
                # Get the user's UID using the email address with Firebase Admin SDK
                user_record = auth.get_user_by_email(email)
    
                # Fetch user data from Firestore using the UID
                user_doc = db.collection('users').document(user_record.uid).get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
    
                    # Update the app's properties with the user's information
                    self.first_name = user_data.get('first_name', 'No Name')
                    self.last_name = user_data.get('last_name', 'No Last Name')
                    self.email = user_data.get('email', 'No Email')
                    self.dob = user_data.get('dob', 'No DOB')
                    self.school_input = user_data.get('school', 'No School')
    
                    # Set the current user's ID
                    self.current_user_id = user_record.uid
    
                    # Transition to the home screen with the updated user info
                    self.screen_manager.current = "home"
                else:
                    self.show_dialog("User data not found.", "Login Failed")
            except auth.AuthError as e:
                self.show_dialog(f"Failed to retrieve user data: {e.message}", "Login Failed")
            except auth.UserNotFoundError:
                self.show_dialog("User not found in Firebase Admin SDK.", "Login Failed")
            except Exception as e:
                self.show_dialog(str(e), "Login Failed")
        else:
            self.show_dialog("Invalid login credentials", "Login Failed")


    def on_login_success(self,user_id):
        self.current_user_id = user_id
        # Directly load user data if the current screen is the account screen
        if self.screen_manager.current_screen.name == 'screen 4':
            self.load_user_data_to_account_page()

   


    
    #LOg out
    def log_out(self):
        # Assuming you use Firebase authentication, invalidate the session
        self.screen_manager.current = 'login'
        # Clear any session-specific data if needed
        self.current_user_id = None
        self.first_name = 'No Name'
        self.last_name = 'No Last Name'
        self.dob = 'No DOB'
        self.email = 'No Email'
        self.school_input = 'No School'

    def send_password_reset_email(self, email):
        try:
            url = f'https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={FIREBASE_API_KEY}'
            payload = {
                'requestType': 'PASSWORD_RESET',
                'email': email
            }
            headers = {
                'Content-Type': 'application/json'
            }
            response = requests.post(url, json=payload, headers=headers)
            response_data = response.json()
    
            if response.status_code == 200:
                self.show_dialog("Password reset email sent. Please check your email. It might take up to 5 minutes to arrive")
            else:
                self.show_dialog(f"Failed to send password reset email: {response_data.get('error', {}).get('message', 'Unknown error')}")
        except Exception as e:
            self.show_dialog(f" {str(e)}")


    
    def calculate_age(self, dob):
        """Calculate age based on the date of birth (dob)."""
        birth_date = datetime.strptime(dob, '%m-%d-%Y')  # Adjust format to match your DOB format
        today = datetime.today()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        return age

    def on_post_ride(self, from_address, to_address, travel_date, time_input, social_media, user_text):
        if not self.validate_ride_inputs(from_address, to_address, travel_date, time_input, social_media):
            self.show_dialog("Please fill in all required fields.")
            return
    
        user_doc = db.collection('users').document(self.current_user_id).get()
        if not user_doc.exists:
            self.show_dialog("User data not found.")
            return
    
        user_data = user_doc.to_dict()
        ride_data = {
            'first_name': user_data['first_name'],
            'age': self.calculate_age(user_data['dob']) if user_data['dob'] else "Unknown",
            'gender': user_data['gender'],
            'school': user_data['school'],
            'from_address': from_address,
            'to_address': to_address,
            'travel_date': travel_date,
            'time_input': time_input,
            'social_media': social_media,
            'user_text': user_text,
            'user_id': self.current_user_id
        }
    
        # Save to Firebase
        doc_ref = db.collection('rides').add(ride_data)
        ride_id = doc_ref[1].id
    
        # Create a ride card and add it to the home screen at the top
        home_screen = self.screen_manager.get_screen('home')
        ride_card = self.create_ride_card(ride_data, ride_id)
        home_screen.ids.rides_list.add_widget(ride_card, index=0)  # Add new card at the top
    
        # Show a success message
        toast("Ride posted successfully!")


    
    def validate_ride_inputs(self, from_address, to_address, travel_date, time_input, social_media):
        # Check if any of the required fields are empty
        if not all([from_address, to_address, travel_date, time_input, social_media]):
            self.show_dialog("Please fill in all required fields.")
            return False
        self.show_dialog("Your ride request has been posted")
        return True
    
    def validate_driver_inputs(self, from_address, to_address, travel_date, time_input, car_input=None, gas_money=None, social_media=None):
        # Assuming car_input, gas_money, and social_media can be optional
        missing_fields = [field for field, value in locals().items() if not value and field != 'self']
        if missing_fields:
            error_message = "Missing fields: " + ", ".join(missing_fields)
            self.show_dialog(error_message)
            return False
        self.show_dialog("Your ride offer has been posted.")
        return True




    def create_ride_card(self, ride_data, ride_id):
        card = MDCard(size_hint=(0.9, None), height="240dp", md_bg_color=(1, 1, 0, 1), radius=[10,])
        card.padding = "8dp"
        card.spacing = "8dp"
        card.orientation = 'horizontal'
    
        
    
        left_column = BoxLayout(orientation='vertical', size_hint_x=None, width="80dp", padding="2dp", spacing="2dp")
        left_column.add_widget(MDLabel(text=f"{ride_data['first_name']} ({ride_data['age']} y.o)", font_style="Subtitle2", halign='center'))
        left_column.add_widget(MDLabel(text=f"{ride_data['gender']}", font_style="Caption", halign='center'))
        left_column.add_widget(MDLabel(text=f"{ride_data['school']}", font_style="Caption", halign='center'))
    
        middle_column = BoxLayout(orientation='vertical', spacing='2dp', padding="2dp")
        middle_column.add_widget(MDLabel(text=f"{ride_data['from_address']} -> {ride_data['to_address']}", font_style="Caption"))
        middle_column.add_widget(MDLabel(text=f"{ride_data['travel_date']} at {ride_data['time_input']}", font_style="Caption"))
        if 'social_media' in ride_data:
            middle_column.add_widget(MDLabel(text=f"{ride_data['social_media']}", font_style="Caption"))
        middle_column.add_widget(MDLabel(text=f" {ride_data['user_text']}", font_style="Caption"))
    
        right_column = BoxLayout(orientation='vertical', spacing='3dp', size_hint_x=None, width="10dp")
        if ride_data.get('user_id') == self.current_user_id:
            delete_btn = MDIconButton(icon="delete", size_hint=(None, None), size=("10dp", "10dp"), pos_hint={"center_x": 0.5})
            # Pass both ride_id and card to the delete_ride method
            delete_btn.bind(on_release=lambda instance: self.delete_ride(ride_id, card))
            right_column.add_widget(delete_btn)

    

    
        card.add_widget(left_column)
        card.add_widget(middle_column)
        card.add_widget(right_column)
    
        return card
    def create_green_ride_card(self, ride_data, ride_id):
        card = MDCard(size_hint=(0.9, None), height="280dp", md_bg_color=(0, 1, 0, 1), radius=[10,])
        card.padding = "8dp"
        card.spacing = "8dp"
        card.orientation = 'horizontal'
    
    
        left_column = BoxLayout(orientation='vertical', size_hint_x=None, width="80dp", padding="2dp", spacing="2dp")
        left_column.add_widget(MDLabel(text=f"{ride_data['first_name']} ({ride_data['age']} y.o)", font_style="Subtitle2", halign='center'))
        left_column.add_widget(MDLabel(text=f"{ride_data['gender']}", font_style="Caption", halign='center'))
        left_column.add_widget(MDLabel(text=f"{ride_data['school']}", font_style="Caption", halign='center'))
    
        middle_column = BoxLayout(orientation='vertical', spacing='2dp', padding="2dp")
        middle_column.add_widget(MDLabel(text=f"{ride_data['from_address']} -> {ride_data['to_address']}", font_style="Caption"))
        middle_column.add_widget(MDLabel(text=f"{ride_data['travel_date']} at {ride_data['time_input']}", font_style="Caption"))
        middle_column.add_widget(MDLabel(text=f"Car: {ride_data['car_input']}", font_style="Caption"))
        if 'social_media' in ride_data:
            middle_column.add_widget(MDLabel(text=f"{ride_data['social_media']}", font_style="Caption"))
        middle_column.add_widget(MDLabel(text=f" {ride_data['user_text']}", font_style="Caption"))
    
        right_column = BoxLayout(orientation='vertical', spacing='3dp', size_hint_x=None, width="40dp")
        right_column.add_widget(MDLabel(text=f"${ride_data['gas_money']}", font_style="H6", theme_text_color="Primary"))


        if ride_data.get('user_id') == self.current_user_id:
            delete_btn = MDIconButton(icon="delete", size_hint=(None, None), size=("10dp", "10dp"), pos_hint={"center_x": 0.5})
            # Pass both ride_id and card to the delete_ride method
            delete_btn.bind(on_release=lambda instance: self.delete_ride(ride_id, card))
            right_column.add_widget(delete_btn)
    
        card.add_widget(left_column)
        card.add_widget(middle_column)
        card.add_widget(right_column)
    
        return card

    
    def on_search_button_press(self, from_address, to_address,travel_date, gas_money,car_input, time_input, social_media):
        if not self.validate_driver_inputs(from_address, to_address, travel_date,gas_money,car_input, time_input, social_media):
            self.show_dialog("Please fill in all required fields.")
            return
        travel_date = self.root.get_screen("driver").ids.travel_date.text
        time_input = self.root.get_screen("driver").ids.time_input.text
        car_input = self.root.get_screen("driver").ids.car_input.text
        gas_money = self.root.get_screen("driver").ids.gas_money.text
        user_text = self.root.get_screen("driver").ids.user_text.text
        social_media=self.root.get_screen("driver").ids.social_media.text
        
    
        user_doc = db.collection('users').document(self.current_user_id).get()
        user_data = user_doc.to_dict()
    
        ride_data = {
            'first_name': user_data.get('first_name', 'N/A'),
            'age': self.calculate_age(user_data.get('dob', '')),
            'gender': user_data.get('gender', 'N/A'),
            'school': user_data.get('school', 'N/A'),
            'from_address': from_address,
            'to_address': to_address,
            'travel_date': travel_date,
            'time_input': time_input,
            'car_input': car_input,
            'gas_money': gas_money,
            'user_text': user_text,
            'social_media':social_media,
            'user_id': self.current_user_id
        }
    
        # Save to Firebase
        doc_ref = db.collection('rides').add(ride_data)
        ride_id = doc_ref[1].id
    
        # Add the card to the home screen
        home_screen = self.screen_manager.get_screen("home")
        green_ride_card = self.create_green_ride_card(ride_data, ride_id)
        home_screen.ids.rides_list.add_widget(green_ride_card, index=0)
    

 
    def delete_ride(self, ride_id, card):
        def confirm_deletion(instance, result):
            if result:
                try:
                    # Check if the card and its parent still exist
                    if card.parent:
                        db.collection('rides').document(ride_id).delete()
                        card.parent.remove_widget(card)
                        toast("Ride deleted successfully")
                    else:
                        toast("Ride card has no parent or was already removed.")
                except Exception as e:
                    toast(f"Error deleting ride: {str(e)}")
            dialog.dismiss()
    
        dialog = MDDialog(
            title="Confirm Deletion",
            text="Are you sure you want to delete this ride?",
            buttons=[
                MDRaisedButton(text="Cancel", on_release=lambda x: dialog.dismiss()),
                MDRaisedButton(text="Delete", on_release=lambda x: confirm_deletion(x, True))
            ]
        )
        dialog.open()

    
    def load_rides(self):
        rides_ref = db.collection('rides').order_by('travel_date', direction=firestore.Query.ASCENDING)  # Ensure sorting is correct
        docs = rides_ref.get()
        home_screen = self.screen_manager.get_screen('home')
        
        home_screen.ids.rides_list.clear_widgets()  # Clear previous rides
        
        for doc in docs:
            ride_data = doc.to_dict()
            if 'gas_money' in ride_data:
                ride_card = self.create_green_ride_card(ride_data, doc.id)
            else:
                ride_card = self.create_ride_card(ride_data, doc.id)
        
            home_screen.ids.rides_list.add_widget(ride_card, index=0)  # Add new card at the top

    
    def delete_past_rides(self):
        today = datetime.now().date()  # Corrected usage
        rides_ref = db.collection('rides')
        try:
            docs = rides_ref.stream()
            for doc in docs:
                ride_data = doc.to_dict()
                if 'travel_date' in ride_data:
                    travel_date = datetime.strptime(ride_data['travel_date'], '%m-%d-%Y').date()
                    if travel_date < today:
                        doc.reference.delete()
                        print(f"Deleted ride with past travel date: {travel_date}")
                        self.refresh_ui_after_deletion()
        except Exception as e:
            print(f"Error during deletion of past rides: {e}")

    def refresh_ui_after_deletion(self):
        """Refresh the UI after deletion to remove the deleted cards."""
        self.load_rides()  # Reload rides to reflect the changes in the UI

    def start_deletion_schedule(self):
        """Schedule the deletion of past rides to run every 24 hours."""
        Clock.schedule_interval(self.delete_past_rides, 60 * 60 * 24)  # 24 hours in seconds
    
    def show_dialog(self, message, title=""):
        if self.dialog:
            self.dialog.dismiss()
        self.dialog = MDDialog(text=message, title=title)
        self.dialog.open()

if __name__ == "__main__":
    Slope().run()
