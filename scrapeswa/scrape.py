import re
import sys
from datetime import datetime
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

timeRE = re.compile(r'\d{1,2}:\d{1,2}[A|P]M', re.M)
driver = None

__all__ = ['init', 'get_round_trip']

def init(set_driver):
    global driver
    driver = set_driver


def get_sw_url(src, dst, outdate, indate, pts=False):
    endpoint = "https://www.southwest.com/air/booking/select.html"

    context = {'adultPassengersCount': '1',
               'departureDate': outdate.strftime("%Y-%m-%d"),  # format '2019-02-04'
               'departureTimeOfDay': 'ALL_DAY',
               'destinationAirportCode': dst,
               'fareType': 'USD' if not pts else 'POINTS',
               'originationAirportCode': src,
               'passengerType': 'ADULT',
               'reset': 'true',
               'returnDate': indate.strftime("%Y-%m-%d"),
               'returnTimeOfDay': 'ALL_DAY',
               'seniorPassengersCount': '0',
               'tripType': 'roundtrip'
               }

    qstr = urlencode(context)
    url = endpoint + "?int=HOMEQBOMAIR&" + qstr
    return url


def parse_flight_price_element(soup, date):
    results = {
        'Flight': re.search(r'[0-9]{1,4}',
                            soup.select_one('.flight-numbers--flight-number .actionable--text').text, re.M).group(),
        'Leave': datetime.strptime(datetime.strftime(date, '%b %d %Y ')
                                   + timeRE.search(soup.select('.air-operations-time-status')[0].text.replace('\n', '')).group(),
                                   '%b %d %Y %I:%M%p'),
        'Arrive': datetime.strptime(datetime.strftime(date, '%b %d %Y ')
                                    + timeRE.search(soup.select('.air-operations-time-status')[1].text.replace('\n', '')).group(),
                                    '%b %d %Y %I:%M%p'),

        'Business': {'fare': None, 'earn': None, 'pts': None, 'ppd': None, 'epd': None},
        'Anytime': {'fare': None, 'earn': None, 'pts': None, 'ppd': None, 'epd': None},
        'Economy': {'fare': None, 'earn': None, 'pts': None, 'ppd': None, 'epd': None}
    }

    find_fare_pts = re.compile(r'\$([0-9]{0,4}),[a-zA-Z\s]*([0-9]{1,5})', re.MULTILINE)

    for fareType in soup.select('.fare-button--button'):
        infoLabel = str(fareType['aria-label'])
        # print(infoLabel)
        if 'Business' in infoLabel:
            result = find_fare_pts.search(infoLabel)
            results["Business"]['fare'] = int(result.group(1))
            results["Business"]['earn'] = int(result.group(2))
        if 'Anytime' in infoLabel:
            result = find_fare_pts.search(infoLabel)
            results["Anytime"]['fare'] = int(result.group(1))
            results["Anytime"]['earn'] = int(result.group(2))
        if 'Get Away' in infoLabel:
            result = find_fare_pts.search(infoLabel)
            results["Economy"]['fare'] = int(result.group(1))
            results["Economy"]['earn'] = int(result.group(2))
    print(results)
    return results


def parse_flight_points_element(soup, dataset):
    rawtxt=soup.text

    for flight in dataset:
        if "# "+flight['Flight'] in rawtxt:
            for fareType in soup.select('.fare-button--button'):
                #print(fareType.text)
                ptsLabel=int(re.search(r'([0-9]{1,6}) Points',fareType.text).group(1))
                #print(ptsLabel)
                infoLabel=str(fareType['aria-label'])
                #print(infoLabel)
                if 'Business' in infoLabel:
                    flight["Business"]['pts']=ptsLabel
                    flight["Business"]['ppd']=ptsLabel/flight["Business"]['fare']
                    flight["Business"]['epd']=flight["Business"]['earn']/flight["Business"]['fare']
                if 'Anytime' in infoLabel:
                    flight["Anytime"]['pts']=ptsLabel
                    flight["Anytime"]['ppd']=ptsLabel/flight["Anytime"]['fare']
                    flight["Anytime"]['epd']=flight["Anytime"]['earn']/flight["Anytime"]['fare']
                if 'Get Away' in infoLabel:
                    flight["Economy"]['pts']=ptsLabel
                    flight["Economy"]['ppd']=ptsLabel/flight["Economy"]['fare']
                    flight["Economy"]['epd']=flight["Economy"]['earn']/flight["Economy"]['fare']


def get_with_retries(url, wait_until, timeout=20, retries=3):
    for n_try in range(retries):
        driver.get(url)
        try:
            WebDriverWait(driver, timeout).until(wait_until)
            return
        except TimeoutException as ex:
            failure = ex
    print(f"Timed out waiting for page to load: {url}", file=sys.stderr)
    raise failure


def get_round_trip(src, dst, out_date, return_date):
    element_to_wait_for = EC.presence_of_element_located((By.CSS_SELECTOR, '#air-booking-fares-0-1 > div.fare-button.fare-button_primary-yellow.select-detail--fare > button'))

    # Get data for flights in dollars
    url = get_sw_url(src, dst, out_date, return_date)
    print(url)
    get_with_retries(url, element_to_wait_for)
    body = BeautifulSoup(driver.find_elements_by_css_selector("body")[0].get_attribute('innerHTML'), features="lxml")

    out_bound = [{'src': src, 'dst': dst, **parse_flight_price_element(element, out_date)}
                 for element in body.select('#air-booking-product-0 div span ul li')]

    return_bound = [{'src': dst, 'dst': src, **parse_flight_price_element(element, return_date)}
                    for element in body.select('#air-booking-product-1 div span ul li')]

    # Get data for flights in points
    url = get_sw_url(src, dst, out_date, return_date, pts=True)
    get_with_retries(url, element_to_wait_for)
    body = BeautifulSoup(driver.find_elements_by_css_selector("body")[0].get_attribute('innerHTML'), features="lxml")

    for element in body.select('#air-booking-product-0 div span ul li'):
        parse_flight_points_element(element, out_bound)

    for element in body.select('#air-booking-product-1 div span ul li'):
        parse_flight_points_element(element, return_bound)

    return out_bound, return_bound
